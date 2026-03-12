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
            "MAX_PROFILES_PER_TEAM": "10",
        },
    ):
        yield


@pytest.fixture
def mock_table():
    table = MagicMock()
    table.put_item = MagicMock()
    table.query.return_value = {"Items": []}
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


def _create_event(body: dict) -> dict:
    return {
        "tenantArn": "arn:aws:iam::042279143912:role/TestTenant-Tenant",
        **body,
    }


class TestRegisterProfileHandler:
    def test_returns_tenant_not_found_when_no_tenant(self, mock_role_session):
        from src.functions.api.register_profile.handler import handler

        mock_role_session.return_value.get_session.side_effect = Exception("no role")

        event = {"team": "marketing", "featureName": "chatbot", "modelId": "test"}
        result = handler(event, MagicMock())

        assert result["lambdaReturnCode"] == 404
        response = json.loads(result["response"])
        assert response["type"] == "not_found_error"

    def test_returns_error_when_team_missing(self, mock_role_session):
        from src.functions.api.register_profile.handler import handler

        event = _create_event({"featureName": "chatbot", "modelId": "test"})
        result = handler(event, MagicMock())

        assert result["lambdaReturnCode"] == 400
        response = json.loads(result["response"])
        assert "team" in response["message"]

    def test_returns_error_when_profile_name_missing(self, mock_role_session):
        from src.functions.api.register_profile.handler import handler

        event = _create_event({"team": "marketing", "modelId": "test"})
        result = handler(event, MagicMock())

        assert result["lambdaReturnCode"] == 400
        response = json.loads(result["response"])
        assert "featureName" in response["message"]

    def test_returns_error_when_model_id_missing(self, mock_role_session):
        from src.functions.api.register_profile.handler import handler

        event = _create_event({"team": "marketing", "featureName": "chatbot"})
        result = handler(event, MagicMock())

        assert result["lambdaReturnCode"] == 400
        response = json.loads(result["response"])
        assert "modelId" in response["message"]

    def test_returns_provisioning_response(self, mock_role_session, mock_table):
        from src.functions.api.register_profile.handler import handler

        event = _create_event(
            {
                "team": "marketing",
                "featureName": "chatbot",
                "modelId": "anthropic.claude-sonnet-4-20250514",
            }
        )
        result = handler(event, MagicMock())

        assert result["lambdaReturnCode"] == 201
        response = json.loads(result["response"])
        assert response["status"] == "PROVISIONING"
        assert response["team"] == "marketing"
        assert response["featureName"] == "chatbot"
        assert response["modelId"] == "anthropic.claude-sonnet-4-20250514"
        assert "id" in response
        assert "createdAt" in response

    def test_writes_correct_dynamo_item(self, mock_role_session, mock_table):
        from src.functions.api.register_profile.handler import handler

        event = _create_event(
            {
                "team": "marketing",
                "featureName": "chatbot",
                "modelId": "anthropic.claude-sonnet-4-20250514",
                "tags": {"env": "demo"},
            }
        )
        handler(event, MagicMock())

        mock_table.put_item.assert_called_once()
        item = mock_table.put_item.call_args[1]["Item"]
        assert item["pk"] == "T#TestTenant#PROFILE"
        assert item["sk"].startswith("PROFILE#")
        assert item["type"] == "PROFILE"
        assert item["team"] == "marketing"
        assert item["feature_name"] == "chatbot"
        assert item["status"] == "PROVISIONING"
        assert item["gsi1pk"] == "T#TestTenant#TEAM#marketing"
        assert item["gsi1sk"] == "PROFILE#chatbot"
        assert item["tags"] == {"env": "demo"}

    def test_rejects_duplicate_active_profile(self, mock_role_session, mock_table):
        from src.functions.api.register_profile.handler import handler

        mock_table.query.return_value = {
            "Items": [{"status": "ACTIVE", "feature_name": "chatbot"}]
        }

        event = _create_event(
            {"team": "marketing", "featureName": "chatbot", "modelId": "test"}
        )
        result = handler(event, MagicMock())

        assert result["lambdaReturnCode"] == 400
        response = json.loads(result["response"])
        assert "already exists" in response["message"]
        mock_table.put_item.assert_not_called()

    def test_rejects_duplicate_provisioning_profile(
        self, mock_role_session, mock_table
    ):
        from src.functions.api.register_profile.handler import handler

        mock_table.query.return_value = {
            "Items": [{"status": "PROVISIONING", "feature_name": "chatbot"}]
        }

        event = _create_event(
            {"team": "marketing", "featureName": "chatbot", "modelId": "test"}
        )
        result = handler(event, MagicMock())

        assert result["lambdaReturnCode"] == 400
        response = json.loads(result["response"])
        assert "already exists" in response["message"]
        mock_table.put_item.assert_not_called()

    def test_allows_reregister_after_failed(self, mock_role_session, mock_table):
        from src.functions.api.register_profile.handler import handler

        # First query (dup check) returns FAILED item, second query (quota) returns same
        mock_table.query.side_effect = [
            {"Items": [{"status": "FAILED", "feature_name": "chatbot"}]},
            {"Items": [{"status": "FAILED", "feature_name": "chatbot"}]},
        ]

        event = _create_event(
            {"team": "marketing", "featureName": "chatbot", "modelId": "test"}
        )
        result = handler(event, MagicMock())

        assert result["lambdaReturnCode"] == 201
        mock_table.put_item.assert_called_once()

    def test_rejects_when_quota_exceeded(self, mock_role_session, mock_table):
        from src.functions.api.register_profile.handler import handler

        active_items = [
            {"status": "ACTIVE", "feature_name": f"profile-{i}"} for i in range(10)
        ]
        # First query (dup check) returns no match, second query (quota) returns 10 active
        mock_table.query.side_effect = [
            {"Items": []},
            {"Items": active_items},
        ]

        event = _create_event(
            {"team": "marketing", "featureName": "new-profile", "modelId": "test"}
        )
        result = handler(event, MagicMock())

        assert result["lambdaReturnCode"] == 400
        response = json.loads(result["response"])
        assert "maximum" in response["message"]
        mock_table.put_item.assert_not_called()

    def test_failed_profiles_excluded_from_quota(self, mock_role_session, mock_table):
        from src.functions.api.register_profile.handler import handler

        items = [
            {"status": "ACTIVE", "feature_name": f"profile-{i}"} for i in range(9)
        ] + [{"status": "FAILED", "feature_name": "failed-one"}]
        # First query (dup check) no match, second query (quota) 9 active + 1 failed
        mock_table.query.side_effect = [
            {"Items": []},
            {"Items": items},
        ]

        event = _create_event(
            {"team": "marketing", "featureName": "new-profile", "modelId": "test"}
        )
        result = handler(event, MagicMock())

        assert result["lambdaReturnCode"] == 201
        mock_table.put_item.assert_called_once()

    def test_quota_uses_env_var_value(self, mock_role_session, mock_table):
        from src.functions.api.register_profile.handler import handler

        active_items = [
            {"status": "ACTIVE", "feature_name": f"profile-{i}"} for i in range(3)
        ]
        mock_table.query.side_effect = [
            {"Items": []},
            {"Items": active_items},
        ]

        with patch.dict(os.environ, {"MAX_PROFILES_PER_TEAM": "3"}):
            event = _create_event(
                {"team": "marketing", "featureName": "new-profile", "modelId": "test"}
            )
            result = handler(event, MagicMock())

        assert result["lambdaReturnCode"] == 400
        response = json.loads(result["response"])
        assert "3" in response["message"]
