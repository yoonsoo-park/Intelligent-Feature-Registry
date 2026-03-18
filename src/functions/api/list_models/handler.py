import os
from typing import Any

import boto3
from aws_lambda_powertools.utilities.typing import LambdaContext
from domain.common.controller import RestUtil
from ncino.handler import ALambdaHandler


class Handler(ALambdaHandler):
    @RestUtil.handle_errors
    def main(self, event: dict, context: LambdaContext) -> Any:
        if not self.tenant:
            return self.return_http_response(*RestUtil.tenant_not_found_response())

        region = os.environ.get("region", "us-east-1")
        allowed_providers = os.environ.get("ALLOWED_PROVIDERS", "anthropic,amazon")
        provider_set = {p.strip().lower() for p in allowed_providers.split(",")}

        bedrock = boto3.client("bedrock", region_name=region)

        cris_response = bedrock.list_inference_profiles(typeEquals="SYSTEM_DEFINED")
        cris_model_ids = set()
        for profile in cris_response.get("inferenceProfileSummaries", []):
            pid = profile.get("inferenceProfileId", "")
            if profile.get("status") != "ACTIVE":
                continue
            if pid.startswith("global."):
                continue
            foundation_model_id = pid.split(".", 1)[1] if "." in pid else pid
            cris_model_ids.add(foundation_model_id)

        fm_response = bedrock.list_foundation_models()
        fm_map = {m["modelId"]: m for m in fm_response.get("modelSummaries", [])}

        models = []
        for model_id in sorted(cris_model_ids):
            fm = fm_map.get(model_id)
            if not fm:
                continue
            if fm.get("providerName", "").lower() not in provider_set:
                continue
            models.append(
                {
                    "modelId": fm["modelId"],
                    "modelName": fm["modelName"],
                    "providerName": fm["providerName"],
                    "inputModalities": fm.get("inputModalities", []),
                    "outputModalities": fm.get("outputModalities", []),
                    "streamingSupported": fm.get("responseStreamingSupported", False),
                }
            )

        models.sort(key=lambda m: (m["providerName"], m["modelName"]))
        return self.return_http_response(200, {"models": models})


handler = Handler.get()
