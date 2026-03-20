import os
from datetime import datetime, timedelta, timezone
from typing import Any

import boto3
import ulid
from aws_lambda_powertools.utilities.typing import LambdaContext
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from domain.common.controller import RestUtil
from domain.common.error import InvalidRequestError, LimitError
from ncino.handler import ALambdaHandler


def _query_all_items(table, **kwargs) -> list[dict]:
    items = []
    while True:
        response = table.query(**kwargs)
        items.extend(response.get("Items", []))
        if "LastEvaluatedKey" not in response:
            break
        kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
    return items


class Handler(ALambdaHandler):
    @RestUtil.handle_errors
    def main(self, event: dict, context: LambdaContext) -> Any:
        if not self.tenant:
            return self.return_http_response(*RestUtil.tenant_not_found_response())

        team = event.get("team")
        feature_name = event.get("featureName")
        model_id = event.get("modelId")
        tags = event.get("tags", {})

        if not team:
            raise InvalidRequestError("Missing required field: team")
        if not feature_name:
            raise InvalidRequestError("Missing required field: featureName")
        if not model_id:
            raise InvalidRequestError("Missing required field: modelId")

        table_name = os.environ["databaseTableName"]
        index_name = os.environ["databaseTableGsi1Name"]
        max_profiles = int(os.environ.get("MAX_PROFILES_PER_TEAM", "10"))
        max_teams = int(os.environ.get("MAX_TEAMS", "2"))
        region = os.environ.get("region", "us-east-1")

        dynamodb = boto3.resource("dynamodb", region_name=region)
        table = dynamodb.Table(table_name)

        gsi1pk = f"TEAM#{team}"

        quota_items = _query_all_items(
            table,
            IndexName=index_name,
            KeyConditionExpression=(
                Key("gsi1pk").eq(gsi1pk) & Key("gsi1sk").begins_with("FEATURE#")
            ),
        )
        active_count = sum(
            1
            for item in quota_items
            if item.get("status") in ("ACTIVE", "PROVISIONING")
        )
        if active_count >= max_profiles:
            raise LimitError(
                f"Team '{team}' has reached the maximum of {max_profiles} profiles"
            )

        is_new_team = active_count == 0
        if is_new_team:
            all_profile_items = _query_all_items(
                table,
                KeyConditionExpression=Key("pk").eq("PROFILE"),
                ProjectionExpression="team",
            )
            existing_teams = {item["team"] for item in all_profile_items}
            if team not in existing_teams and len(existing_teams) >= max_teams:
                raise LimitError(
                    f"Maximum number of teams ({max_teams}) has been reached"
                )

        profile_id = str(ulid.new())
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        expires_at = int((now + timedelta(hours=1)).timestamp())

        item = {
            "pk": "PROFILE",
            "sk": f"TEAM#{team}#FEATURE#{feature_name}#MODEL#{model_id}",
            "type": "PROFILE",
            "profile_id": profile_id,
            "team": team,
            "feature_name": feature_name,
            "model_id": model_id,
            "status": "PROVISIONING",
            "inference_profile_arn": None,
            "inference_profile_id": None,
            "error_message": None,
            "tags": tags,
            "created_at": now_iso,
            "updated_at": now_iso,
            "expires_at": expires_at,
            "gsi1pk": gsi1pk,
            "gsi1sk": f"FEATURE#{feature_name}#MODEL#{model_id}",
        }

        try:
            table.put_item(
                Item=item,
                ConditionExpression="attribute_not_exists(pk) OR #status IN (:failed, :deleted)",
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={":failed": "FAILED", ":deleted": "DELETED"},
            )
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise InvalidRequestError(
                    f"Profile already exists for team={team}, featureName={feature_name}, modelId={model_id}"
                )
            raise

        return self.return_http_response(
            201,
            {
                "id": profile_id,
                "team": team,
                "featureName": feature_name,
                "modelId": model_id,
                "status": "PROVISIONING",
                "createdAt": now_iso,
            },
        )


handler = Handler.get()
