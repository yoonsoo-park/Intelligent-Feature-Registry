import json
import os
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def mock_env_vars():
    with patch.dict(
        os.environ,
        {
            "region": "us-east-1",
            "featureRoleArn": "arn:aws:iam::042279143912:role/test-role",
            "service": "intel-feature-registry",
            "ALLOWED_PROVIDERS": "anthropic,amazon",
        },
    ):
        yield


ANTHROPIC_SONNET_CRIS = {
    "inferenceProfileId": "us.anthropic.claude-sonnet-4-20250514-v1:0",
    "inferenceProfileName": "US Claude Sonnet 4",
    "status": "ACTIVE",
    "type": "SYSTEM_DEFINED",
}

ANTHROPIC_SONNET_FM = {
    "modelId": "anthropic.claude-sonnet-4-20250514-v1:0",
    "modelName": "Claude Sonnet 4",
    "providerName": "Anthropic",
    "inputModalities": ["TEXT", "IMAGE"],
    "outputModalities": ["TEXT"],
    "responseStreamingSupported": True,
    "modelLifecycle": {"status": "ACTIVE"},
}

AMAZON_NOVA_CRIS = {
    "inferenceProfileId": "us.amazon.nova-pro-v1:0",
    "inferenceProfileName": "US Nova Pro",
    "status": "ACTIVE",
    "type": "SYSTEM_DEFINED",
}

AMAZON_NOVA_FM = {
    "modelId": "amazon.nova-pro-v1:0",
    "modelName": "Nova Pro",
    "providerName": "Amazon",
    "inputModalities": ["TEXT", "IMAGE"],
    "outputModalities": ["TEXT"],
    "responseStreamingSupported": True,
    "modelLifecycle": {"status": "ACTIVE"},
}

META_LLAMA_CRIS = {
    "inferenceProfileId": "us.meta.llama3-3-70b-instruct-v1:0",
    "inferenceProfileName": "US Meta Llama 3.3 70B Instruct",
    "status": "ACTIVE",
    "type": "SYSTEM_DEFINED",
}

META_LLAMA_FM = {
    "modelId": "meta.llama3-3-70b-instruct-v1:0",
    "modelName": "Llama 3.3 70B Instruct",
    "providerName": "Meta",
    "inputModalities": ["TEXT"],
    "outputModalities": ["TEXT"],
    "responseStreamingSupported": True,
    "modelLifecycle": {"status": "ACTIVE"},
}

GLOBAL_CRIS = {
    "inferenceProfileId": "global.anthropic.claude-sonnet-4-20250514-v1:0",
    "inferenceProfileName": "Global Claude Sonnet 4",
    "status": "ACTIVE",
    "type": "SYSTEM_DEFINED",
}


@pytest.fixture
def mock_bedrock():
    client = MagicMock()
    client.list_inference_profiles.return_value = {"inferenceProfileSummaries": []}
    client.list_foundation_models.return_value = {"modelSummaries": []}
    return client


@pytest.fixture
def mock_boto3(mock_bedrock):
    with patch("src.functions.api.list_models.handler.boto3") as m:
        m.client.return_value = mock_bedrock
        yield m


@pytest.fixture
def mock_role_session():
    with patch("ncino.handler.RoleSessionCache") as mock_cache_cls:
        yield mock_cache_cls


def _create_event() -> dict:
    return {"tenantArn": "arn:aws:iam::042279143912:role/TestTenant-Tenant"}


class TestListModelsHandler:
    def test_returns_tenant_not_found_when_no_tenant(
        self, mock_role_session, mock_boto3
    ):
        from src.functions.api.list_models.handler import handler

        mock_role_session.return_value.get_session.side_effect = Exception("no role")

        result = handler({}, MagicMock())

        assert result["lambdaReturnCode"] == 404
        response = json.loads(result["response"])
        assert response["type"] == "not_found_error"

    def test_returns_empty_list_when_no_cris_profiles(
        self, mock_role_session, mock_boto3, mock_bedrock
    ):
        from src.functions.api.list_models.handler import handler

        result = handler(_create_event(), MagicMock())

        assert result["lambdaReturnCode"] == 200
        response = json.loads(result["response"])
        assert response["models"] == []

    def test_filters_by_allowed_provider(
        self, mock_role_session, mock_boto3, mock_bedrock
    ):
        from src.functions.api.list_models.handler import handler

        mock_bedrock.list_inference_profiles.return_value = {
            "inferenceProfileSummaries": [
                ANTHROPIC_SONNET_CRIS,
                AMAZON_NOVA_CRIS,
                META_LLAMA_CRIS,
            ]
        }
        mock_bedrock.list_foundation_models.return_value = {
            "modelSummaries": [ANTHROPIC_SONNET_FM, AMAZON_NOVA_FM, META_LLAMA_FM]
        }

        result = handler(_create_event(), MagicMock())

        assert result["lambdaReturnCode"] == 200
        response = json.loads(result["response"])
        provider_names = [m["providerName"] for m in response["models"]]
        assert "Anthropic" in provider_names
        assert "Amazon" in provider_names
        assert "Meta" not in provider_names

    def test_excludes_global_prefix_profiles(
        self, mock_role_session, mock_boto3, mock_bedrock
    ):
        from src.functions.api.list_models.handler import handler

        mock_bedrock.list_inference_profiles.return_value = {
            "inferenceProfileSummaries": [ANTHROPIC_SONNET_CRIS, GLOBAL_CRIS]
        }
        mock_bedrock.list_foundation_models.return_value = {
            "modelSummaries": [ANTHROPIC_SONNET_FM]
        }

        result = handler(_create_event(), MagicMock())

        assert result["lambdaReturnCode"] == 200
        response = json.loads(result["response"])
        assert len(response["models"]) == 1
        assert response["models"][0]["modelId"] == ANTHROPIC_SONNET_FM["modelId"]

    def test_includes_non_us_regional_prefixes(
        self, mock_role_session, mock_boto3, mock_bedrock
    ):
        from src.functions.api.list_models.handler import handler

        eu_cris = {
            "inferenceProfileId": "eu.anthropic.claude-sonnet-4-20250514-v1:0",
            "inferenceProfileName": "EU Claude Sonnet 4",
            "status": "ACTIVE",
            "type": "SYSTEM_DEFINED",
        }
        ap_cris = {
            "inferenceProfileId": "ap.amazon.nova-pro-v1:0",
            "inferenceProfileName": "AP Nova Pro",
            "status": "ACTIVE",
            "type": "SYSTEM_DEFINED",
        }
        mock_bedrock.list_inference_profiles.return_value = {
            "inferenceProfileSummaries": [eu_cris, ap_cris]
        }
        mock_bedrock.list_foundation_models.return_value = {
            "modelSummaries": [ANTHROPIC_SONNET_FM, AMAZON_NOVA_FM]
        }

        result = handler(_create_event(), MagicMock())

        assert result["lambdaReturnCode"] == 200
        response = json.loads(result["response"])
        model_ids = [m["modelId"] for m in response["models"]]
        assert ANTHROPIC_SONNET_FM["modelId"] in model_ids
        assert AMAZON_NOVA_FM["modelId"] in model_ids

    def test_excludes_inactive_cris_profiles(
        self, mock_role_session, mock_boto3, mock_bedrock
    ):
        from src.functions.api.list_models.handler import handler

        inactive_cris = {**ANTHROPIC_SONNET_CRIS, "status": "DEPRECATED"}
        mock_bedrock.list_inference_profiles.return_value = {
            "inferenceProfileSummaries": [inactive_cris]
        }
        mock_bedrock.list_foundation_models.return_value = {
            "modelSummaries": [ANTHROPIC_SONNET_FM]
        }

        result = handler(_create_event(), MagicMock())

        assert result["lambdaReturnCode"] == 200
        response = json.loads(result["response"])
        assert response["models"] == []

    def test_returns_correctly_transformed_model(
        self, mock_role_session, mock_boto3, mock_bedrock
    ):
        from src.functions.api.list_models.handler import handler

        mock_bedrock.list_inference_profiles.return_value = {
            "inferenceProfileSummaries": [ANTHROPIC_SONNET_CRIS]
        }
        mock_bedrock.list_foundation_models.return_value = {
            "modelSummaries": [ANTHROPIC_SONNET_FM]
        }

        result = handler(_create_event(), MagicMock())

        assert result["lambdaReturnCode"] == 200
        response = json.loads(result["response"])
        assert len(response["models"]) == 1
        model = response["models"][0]
        assert model == {
            "modelId": "anthropic.claude-sonnet-4-20250514-v1:0",
            "modelName": "Claude Sonnet 4",
            "providerName": "Anthropic",
            "inputModalities": ["TEXT", "IMAGE"],
            "outputModalities": ["TEXT"],
            "streamingSupported": True,
        }

    def test_sorts_by_provider_then_name(
        self, mock_role_session, mock_boto3, mock_bedrock
    ):
        from src.functions.api.list_models.handler import handler

        mock_bedrock.list_inference_profiles.return_value = {
            "inferenceProfileSummaries": [AMAZON_NOVA_CRIS, ANTHROPIC_SONNET_CRIS]
        }
        mock_bedrock.list_foundation_models.return_value = {
            "modelSummaries": [AMAZON_NOVA_FM, ANTHROPIC_SONNET_FM]
        }

        result = handler(_create_event(), MagicMock())

        assert result["lambdaReturnCode"] == 200
        response = json.loads(result["response"])
        providers = [m["providerName"] for m in response["models"]]
        assert providers == ["Amazon", "Anthropic"]

    def test_provider_filter_is_case_insensitive(
        self, mock_role_session, mock_boto3, mock_bedrock
    ):
        from src.functions.api.list_models.handler import handler

        mock_bedrock.list_inference_profiles.return_value = {
            "inferenceProfileSummaries": [ANTHROPIC_SONNET_CRIS]
        }
        mock_bedrock.list_foundation_models.return_value = {
            "modelSummaries": [ANTHROPIC_SONNET_FM]
        }

        with patch.dict(os.environ, {"ALLOWED_PROVIDERS": "Anthropic"}):
            result = handler(_create_event(), MagicMock())

        assert result["lambdaReturnCode"] == 200
        response = json.loads(result["response"])
        assert len(response["models"]) == 1
