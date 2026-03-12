import os
from datetime import datetime, timezone
from typing import Any

import boto3
from aws_lambda_powertools.utilities.data_classes.dynamo_db_stream_event import (
    DynamoDBStreamEvent,
)
from aws_lambda_powertools.utilities.typing import LambdaContext
from ncino.handler import ALambdaHandler

SUPPORTED_MODELS = {
    "anthropic.claude-sonnet-4-20250514": "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-sonnet-4-20250514-v1:0",
    "anthropic.claude-sonnet-4-20250514-v1:0": "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-sonnet-4-20250514-v1:0",
    "anthropic.claude-3-5-sonnet-20241022-v2:0": "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-5-sonnet-20241022-v2:0",
    "anthropic.claude-3-haiku-20240307-v1:0": "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-haiku-20240307-v1:0",
    "anthropic.claude-3-5-haiku-20241022-v1:0": "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-5-haiku-20241022-v1:0",
    "amazon.nova-micro-v1:0": "arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-micro-v1:0",
    "amazon.nova-lite-v1:0": "arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-lite-v1:0",
    "amazon.nova-pro-v1:0": "arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-pro-v1:0",
}


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
                # Verify item still exists and is still PROVISIONING before calling Bedrock
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
                self._update_profile_status(
                    pk, sk, "ACTIVE", profile_arn, inf_profile_id
                )
                self.logger.info(
                    f"Successfully provisioned inference profile {inf_profile_id} "
                    f"for profile {profile_id}"
                )
            except Exception as ex:
                self.logger.error(
                    f"Failed to provision inference profile for profile {profile_id}: {ex}"
                )
                self._update_profile_status(pk, sk, "FAILED", error_message=str(ex))

    def _create_inference_profile(
        self,
        profile_id: str,
        team: str,
        feature_name: str,
        model_id: str,
        tags: dict,
    ) -> tuple[str, str]:
        region = os.environ.get("region", "us-east-1")

        model_arn = SUPPORTED_MODELS.get(model_id)
        if not model_arn:
            model_arn = f"arn:aws:bedrock:{region}::foundation-model/{model_id}"

        inf_profile_name = f"ig-{team}-{feature_name}-{profile_id[:8]}"

        bedrock_client = boto3.client("bedrock", region_name=region)

        bedrock_tags = [
            {"key": "team", "value": team},
            {"key": "feature", "value": feature_name},
            {"key": "profile_id", "value": profile_id},
            {"key": "managed_by", "value": "intelligent-feature-registry"},
        ]
        if isinstance(tags, dict):
            for k, v in tags.items():
                bedrock_tags.append({"key": str(k), "value": str(v)})

        response = bedrock_client.create_inference_profile(
            inferenceProfileName=inf_profile_name,
            description=f"ig.{team}.{feature_name}",
            modelSource={"copyFrom": model_arn},
            tags=bedrock_tags,
        )

        profile_arn = response["inferenceProfileArn"]
        inf_profile_id = profile_arn.split("/")[-1]

        return profile_arn, inf_profile_id

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
        expr_names = {"#status": "status"}
        expr_values: dict = {":status": status, ":now": now}

        if profile_arn:
            update_expr += ", inference_profile_arn = :arn, inference_profile_id = :pid"
            expr_values[":arn"] = profile_arn
            expr_values[":pid"] = profile_id

        if error_message:
            update_expr += ", error_message = :err"
            expr_values[":err"] = error_message[:1000]

        table.update_item(
            Key={"pk": pk, "sk": sk},
            UpdateExpression=update_expr,
            ExpressionAttributeNames=expr_names,
            ExpressionAttributeValues=expr_values,
        )


handler = Handler.get()
