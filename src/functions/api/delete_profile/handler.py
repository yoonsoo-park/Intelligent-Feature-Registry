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

        key = {
            "pk": "PROFILE",
            "sk": f"TEAM#{team}#FEATURE#{feature_name}#MODEL#{model_id}",
        }

        response = table.get_item(Key=key, ConsistentRead=True)
        item = response.get("Item")
        if not item:
            raise NotFoundError(
                f"No profile found for team={team}, featureName={feature_name}, modelId={model_id}"
            )

        status = item.get("status")
        inference_profile_arn = item.get("inference_profile_arn")

        if status == "ACTIVE" and inference_profile_arn:
            bedrock_client = boto3.client("bedrock", region_name=region)
            try:
                bedrock_client.delete_inference_profile(
                    inferenceProfileIdentifier=inference_profile_arn
                )
            except bedrock_client.exceptions.ResourceNotFoundException:
                pass

        table.delete_item(Key=key)

        return self.return_http_response(
            200,
            {
                "id": item.get("profile_id"),
                "team": team,
                "featureName": feature_name,
                "modelId": model_id,
                "status": "DELETED",
            },
        )


handler = Handler.get()
