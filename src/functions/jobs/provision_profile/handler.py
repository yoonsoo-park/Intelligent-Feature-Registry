import os
from datetime import datetime, timedelta, timezone
from typing import Any

import boto3
from aws_lambda_powertools.utilities.data_classes.dynamo_db_stream_event import (
    DynamoDBStreamEvent,
)
from aws_lambda_powertools.utilities.typing import LambdaContext
from ncino.handler import ALambdaHandler


class Handler(ALambdaHandler):
    def main(self, event: dict, context: LambdaContext) -> Any:
        e = DynamoDBStreamEvent(event)

        for record in e.records:
            if not record.dynamodb or not record.dynamodb.new_image:
                continue

            new_image = record.dynamodb.new_image
            profile_id = new_image["profile_id"]
            team = new_image["team"]
            feature_name = new_image["feature_name"]
            model_id = new_image["model_id"]
            tags = new_image.get("tags", {})
            pk = new_image["pk"]
            sk = new_image["sk"]

            self.logger.info(
                f"Provisioning inference profile for profile {profile_id} "
                f"(team={team}, feature={feature_name}, model={model_id})"
            )

            try:
                table_name = os.environ["databaseTableName"]
                region = os.environ.get("region", "us-east-1")
                dynamodb = boto3.resource("dynamodb", region_name=region)
                table = dynamodb.Table(table_name)
                current = table.get_item(Key={"pk": pk, "sk": sk}).get("Item")
                if not current or current.get("status") != "PROVISIONING":
                    self.logger.info(
                        f"Skipping provisioning for profile {profile_id}: "
                        f"item {'not found' if not current else 'status=' + current.get('status', 'unknown')}"
                    )
                    continue

                profile_arn, inf_profile_id = self._create_inference_profile(
                    profile_id, team, feature_name, model_id, tags
                )
                try:
                    self._update_profile_status(
                        pk, sk, "ACTIVE", profile_arn, inf_profile_id
                    )
                except Exception:
                    self.logger.error(
                        f"DDB update failed after creating inference profile {profile_arn}, "
                        f"rolling back Bedrock resource"
                    )
                    self._rollback_inference_profile(profile_arn)
                    raise
                self.logger.info(
                    f"Successfully provisioned inference profile {inf_profile_id} "
                    f"for profile {profile_id}"
                )
            except Exception as ex:
                self.logger.error(
                    f"Failed to provision inference profile for profile {profile_id}: {ex}"
                )
                self._update_profile_status(pk, sk, "FAILED", error_message=str(ex))

    def _resolve_model_source(self, model_id: str, region: str, bedrock_client) -> str:
        cris_response = bedrock_client.list_inference_profiles(
            typeEquals="SYSTEM_DEFINED"
        )
        for profile in cris_response.get("inferenceProfileSummaries", []):
            if profile.get("status") != "ACTIVE":
                continue
            pid = profile.get("inferenceProfileId", "")
            if pid.startswith("global."):
                continue
            foundation_model_id = pid.split(".", 1)[1] if "." in pid else pid
            if foundation_model_id == model_id:
                return profile["inferenceProfileArn"]
        return f"arn:aws:bedrock:{region}::foundation-model/{model_id}"

    # TODO(phase-2): reconciliation job to detect orphaned Bedrock profiles after DDB TTL expiry
    def _create_inference_profile(
        self,
        profile_id: str,
        team: str,
        feature_name: str,
        model_id: str,
        tags: dict,
    ) -> tuple[str, str]:
        region = os.environ.get("region", "us-east-1")
        bedrock_client = boto3.client("bedrock", region_name=region)

        model_arn = self._resolve_model_source(model_id, region, bedrock_client)

        model_short = model_id.rsplit(".", 1)[-1] if "." in model_id else model_id
        inf_profile_name = f"ig-{team}-{feature_name}-{model_short}-{profile_id[:8]}"

        bedrock_tags = [
            {"key": "team", "value": team},
            {"key": "feature", "value": feature_name},
            {"key": "model_id", "value": model_id},
            {"key": "profile_id", "value": profile_id},
            {
                "key": "managed_by",
                "value": "intel-feature-registry",
            },  # is this necessary?
        ]
        if isinstance(tags, dict):
            for k, v in tags.items():
                bedrock_tags.append({"key": str(k), "value": str(v)})

        response = bedrock_client.create_inference_profile(
            inferenceProfileName=inf_profile_name,
            description=f"ig.{team}.{feature_name}.{model_short}",
            modelSource={"copyFrom": model_arn},
            tags=bedrock_tags,
        )

        profile_arn = response["inferenceProfileArn"]
        inf_profile_id = profile_arn.split("/")[-1]

        return profile_arn, inf_profile_id

    def _rollback_inference_profile(self, profile_arn: str) -> None:
        region = os.environ.get("region", "us-east-1")
        bedrock_client = boto3.client("bedrock", region_name=region)
        try:
            bedrock_client.delete_inference_profile(
                inferenceProfileIdentifier=profile_arn
            )
            self.logger.info(f"Rolled back inference profile {profile_arn}")
        except Exception as rollback_ex:
            self.logger.error(
                f"Failed to rollback inference profile {profile_arn}: {rollback_ex}"
            )

    def _update_profile_status(
        self,
        pk: str,
        sk: str,
        status: str,
        profile_arn: str | None = None,
        profile_id: str | None = None,
        error_message: str | None = None,
    ) -> None:
        table_name = os.environ["databaseTableName"]
        region = os.environ.get("region", "us-east-1")
        dynamodb = boto3.resource("dynamodb", region_name=region)
        table = dynamodb.Table(table_name)
        now = datetime.now(timezone.utc).isoformat()

        update_expr = "SET #status = :status, updated_at = :now"
        remove_attrs = []
        expr_names = {"#status": "status"}
        expr_values: dict = {":status": status, ":now": now}

        if profile_arn:
            update_expr += ", inference_profile_arn = :arn, inference_profile_id = :pid"
            expr_values[":arn"] = profile_arn
            expr_values[":pid"] = profile_id

        if error_message:
            update_expr += ", error_message = :err"
            expr_values[":err"] = error_message[:1000]

        if status == "ACTIVE":
            remove_attrs.append("expires_at")
        elif status == "FAILED":
            expires_at = int(
                (datetime.now(timezone.utc) + timedelta(days=7)).timestamp()
            )
            update_expr += ", expires_at = :ttl"
            expr_values[":ttl"] = expires_at

        if remove_attrs:
            update_expr += " REMOVE " + ", ".join(remove_attrs)

        table.update_item(
            Key={"pk": pk, "sk": sk},
            UpdateExpression=update_expr,
            ConditionExpression="attribute_exists(pk)",
            ExpressionAttributeNames=expr_names,
            ExpressionAttributeValues=expr_values,
        )


handler = Handler.get()
