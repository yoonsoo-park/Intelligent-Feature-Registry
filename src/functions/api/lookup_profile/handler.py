import os
from typing import Any

from aws_lambda_powertools.utilities.typing import LambdaContext
from boto3.dynamodb.conditions import Key
from domain.common.controller import RestUtil
from domain.common.error import InvalidRequestError, NotFoundError
from ncino.handler import ALambdaHandler


class Handler(ALambdaHandler):
    @RestUtil.handle_errors
    def main(self, event: dict, context: LambdaContext) -> Any:
        if not self.tenant:
            return self.return_http_response(*RestUtil.tenant_not_found_response())

        team = event.get("team")
        feature_name = event.get("featureName")

        if not team:
            raise InvalidRequestError("Missing required query parameter: team")
        if not feature_name:
            raise InvalidRequestError("Missing required query parameter: featureName")

        table_name = os.environ["databaseTableName"]
        index_name = os.environ["databaseTableGsi1Name"]

        dynamodb = self.assume_profile_role().resource("dynamodb")
        table = dynamodb.Table(table_name)

        response = table.query(
            IndexName=index_name,
            KeyConditionExpression=(
                Key("gsi1pk").eq(f"T#{self.tenant_id}#TEAM#{team}")
                & Key("gsi1sk").eq(f"PROFILE#{feature_name}")
            ),
        )

        items = response.get("Items", [])
        if not items:
            raise NotFoundError(
                f"No profile found for team={team}, featureName={feature_name}"
            )

        item = items[0]
        status = item.get("status")

        result: dict[str, Any] = {
            "id": item.get("profile_id"),
            "team": item.get("team"),
            "featureName": item.get("feature_name"),
            "modelId": item.get("model_id"),
            "status": status,
            "createdAt": item.get("created_at"),
            "updatedAt": item.get("updated_at"),
        }

        if status == "ACTIVE":
            result["inferenceProfileArn"] = item.get("inference_profile_arn")
            result["inferenceProfileId"] = item.get("inference_profile_id")
        elif status == "FAILED":
            result["error"] = item.get("error_message")

        return self.return_http_response(200, result)


handler = Handler.get()
