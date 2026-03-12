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
            "databaseTableName": "test-table",
            "databaseTableGsi1Name": "gsi1",
            "service": "intelligent-gateway",
        },
    ):
        yield


@pytest.fixture
def mock_table():
    table = MagicMock()
    return table


@pytest.fixture
def mock_session(mock_table):
    session = MagicMock()
    dynamodb = MagicMock()
    dynamodb.Table.return_value = mock_table
    session.resource.return_value = dynamodb
    return session


@pytest.fixture
def mock_role_session(mock_session):
    with patch("ncino.handler.RoleSessionCache") as mock_cache_cls:
        mock_cache_cls.return_value.get_session.return_value = mock_session
        yield mock_cache_cls


def _create_event(params: dict) -> dict:
    return {
        "tenantArn": "arn:aws:iam::042279143912:role/TestTenant-Tenant",
        **params,
    }


class TestLookupProfileHandler:
    def test_returns_tenant_not_found_when_no_tenant(self, mock_role_session):
        from src.functions.api.lookup_profile.handler import handler

        mock_role_session.return_value.get_session.side_effect = Exception("no role")

        event = {"team": "marketing", "featureName": "chatbot"}
        result = handler(event, MagicMock())

        assert result["lambdaReturnCode"] == 404

    def test_returns_error_when_team_missing(self, mock_role_session):
        from src.functions.api.lookup_profile.handler import handler

        event = _create_event({"featureName": "chatbot"})
        result = handler(event, MagicMock())

        assert result["lambdaReturnCode"] == 400
        response = json.loads(result["response"])
        assert "team" in response["message"]

    def test_returns_error_when_profile_name_missing(self, mock_role_session):
        from src.functions.api.lookup_profile.handler import handler

        event = _create_event({"team": "marketing"})
        result = handler(event, MagicMock())

        assert result["lambdaReturnCode"] == 400
        response = json.loads(result["response"])
        assert "featureName" in response["message"]

    def test_returns_not_found_when_no_items(self, mock_role_session, mock_table):
        from src.functions.api.lookup_profile.handler import handler

        mock_table.query.return_value = {"Items": []}

        event = _create_event({"team": "marketing", "featureName": "chatbot"})
        result = handler(event, MagicMock())

        assert result["lambdaReturnCode"] == 404

    def test_returns_active_profile_with_inference(self, mock_role_session, mock_table):
        from src.functions.api.lookup_profile.handler import handler

        mock_table.query.return_value = {
            "Items": [
                {
                    "profile_id": "01HXYZ",
                    "team": "marketing",
                    "feature_name": "chatbot",
                    "model_id": "anthropic.claude-sonnet-4-20250514",
                    "status": "ACTIVE",
                    "inference_profile_arn": "arn:aws:bedrock:us-east-1:042279143912:application-inference-profile/abc123",
                    "inference_profile_id": "abc123",
                    "created_at": "2026-03-10T15:00:00Z",
                    "updated_at": "2026-03-10T15:00:05Z",
                }
            ]
        }

        event = _create_event({"team": "marketing", "featureName": "chatbot"})
        result = handler(event, MagicMock())

        assert result["lambdaReturnCode"] == 200
        response = json.loads(result["response"])
        assert response["status"] == "ACTIVE"
        assert (
            response["inferenceProfileArn"]
            == "arn:aws:bedrock:us-east-1:042279143912:application-inference-profile/abc123"
        )
        assert response["inferenceProfileId"] == "abc123"

    def test_returns_failed_profile_with_error(self, mock_role_session, mock_table):
        from src.functions.api.lookup_profile.handler import handler

        mock_table.query.return_value = {
            "Items": [
                {
                    "profile_id": "01HXYZ",
                    "team": "marketing",
                    "feature_name": "chatbot",
                    "model_id": "anthropic.claude-sonnet-4-20250514",
                    "status": "FAILED",
                    "error_message": "Model not available",
                    "created_at": "2026-03-10T15:00:00Z",
                    "updated_at": "2026-03-10T15:00:05Z",
                }
            ]
        }

        event = _create_event({"team": "marketing", "featureName": "chatbot"})
        result = handler(event, MagicMock())

        assert result["lambdaReturnCode"] == 200
        response = json.loads(result["response"])
        assert response["status"] == "FAILED"
        assert response["error"] == "Model not available"

    def test_returns_provisioning_profile(self, mock_role_session, mock_table):
        from src.functions.api.lookup_profile.handler import handler

        mock_table.query.return_value = {
            "Items": [
                {
                    "profile_id": "01HXYZ",
                    "team": "marketing",
                    "feature_name": "chatbot",
                    "model_id": "anthropic.claude-sonnet-4-20250514",
                    "status": "PROVISIONING",
                    "created_at": "2026-03-10T15:00:00Z",
                    "updated_at": "2026-03-10T15:00:00Z",
                }
            ]
        }

        event = _create_event({"team": "marketing", "featureName": "chatbot"})
        result = handler(event, MagicMock())

        assert result["lambdaReturnCode"] == 200
        response = json.loads(result["response"])
        assert response["status"] == "PROVISIONING"
        assert "inferenceProfileArn" not in response
