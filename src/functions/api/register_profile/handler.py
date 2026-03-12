import os
from datetime import datetime, timezone
from typing import Any

import ulid
from aws_lambda_powertools.utilities.typing import LambdaContext
from boto3.dynamodb.conditions import Key
from domain.common.controller import RestUtil
from domain.common.error import InvalidRequestError, LimitError
from ncino.handler import ALambdaHandler


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

        dynamodb = self.assume_profile_role().resource("dynamodb")
        table = dynamodb.Table(table_name)

        gsi1pk = f"T#{self.tenant_id}#TEAM#{team}"

        # Duplicate check: exact match on team + profileName
        dup_response = table.query(
            IndexName=index_name,
            KeyConditionExpression=(
                Key("gsi1pk").eq(gsi1pk) & Key("gsi1sk").eq(f"PROFILE#{feature_name}")
            ),
        )
        for existing in dup_response.get("Items", []):
            if existing.get("status") in ("ACTIVE", "PROVISIONING"):
                raise InvalidRequestError(
                    f"Profile already exists for team={team}, featureName={feature_name}"
                )

        # Quota check: count ACTIVE + PROVISIONING profiles for this team
        quota_response = table.query(
            IndexName=index_name,
            KeyConditionExpression=(
                Key("gsi1pk").eq(gsi1pk) & Key("gsi1sk").begins_with("PROFILE#")
            ),
        )
        active_count = sum(
            1
            for item in quota_response.get("Items", [])
            if item.get("status") in ("ACTIVE", "PROVISIONING")
        )
        if active_count >= max_profiles:
            raise LimitError(
                f"Team '{team}' has reached the maximum of {max_profiles} profiles"
            )

        profile_id = str(ulid.new())
        now = datetime.now(timezone.utc).isoformat()

        item = {
            "pk": f"T#{self.tenant_id}#PROFILE",
            "sk": f"PROFILE#{profile_id}",
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
            "created_at": now,
            "updated_at": now,
            "gsi1pk": gsi1pk,
            "gsi1sk": f"PROFILE#{feature_name}",
        }

        table.put_item(Item=item)

        return self.return_http_response(
            201,
            {
                "id": profile_id,
                "team": team,
                "featureName": feature_name,
                "modelId": model_id,
                "status": "PROVISIONING",
                "createdAt": now,
            },
        )


handler = Handler.get()
