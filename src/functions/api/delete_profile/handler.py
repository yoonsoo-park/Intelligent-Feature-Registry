import os
from typing import Any

import boto3
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
        region = os.environ.get("region", "us-east-1")

        dynamodb = self.assume_profile_role().resource("dynamodb")
        table = dynamodb.Table(table_name)

        # Look up the profile via GSI1
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
        pk = item["pk"]
        sk = item["sk"]
        status = item.get("status")
        inference_profile_arn = item.get("inference_profile_arn")

        # If ACTIVE with an inference profile ARN, delete the Bedrock profile
        if status == "ACTIVE" and inference_profile_arn:
            bedrock_client = boto3.client("bedrock", region_name=region)
            bedrock_client.delete_inference_profile(
                inferenceProfileIdentifier=inference_profile_arn
            )

        # Delete the DynamoDB item
        table.delete_item(Key={"pk": pk, "sk": sk})

        return self.return_http_response(
            200,
            {
                "id": item.get("profile_id"),
                "team": team,
                "featureName": feature_name,
                "status": "DELETED",
            },
        )


handler = Handler.get()
