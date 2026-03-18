import os
from typing import Any

import boto3
from aws_lambda_powertools.utilities.typing import LambdaContext
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
        model_id = event.get("modelId")

        if not team:
            raise InvalidRequestError("Missing required query parameter: team")
        if not feature_name:
            raise InvalidRequestError("Missing required query parameter: featureName")
        if not model_id:
            raise InvalidRequestError("Missing required query parameter: modelId")

        table_name = os.environ["databaseTableName"]
        region = os.environ.get("region", "us-east-1")

        dynamodb = boto3.resource("dynamodb", region_name=region)
        table = dynamodb.Table(table_name)

        response = table.get_item(
            Key={
                "pk": "PROFILE",
                "sk": f"TEAM#{team}#FEATURE#{feature_name}#MODEL#{model_id}",
            },
            ConsistentRead=True,
        )

        item = response.get("Item")
        if not item:
            raise NotFoundError(
                f"No profile found for team={team}, featureName={feature_name}, modelId={model_id}"
            )

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
