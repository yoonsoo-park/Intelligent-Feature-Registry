import json
import os
import time
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError


@pytest.fixture(autouse=True)
def mock_env_vars():
    with patch.dict(
        os.environ,
        {
            "region": "us-east-1",
            "featureRoleArn": "arn:aws:iam::042279143912:role/test-role",
            "databaseTableName": "test-table",
            "databaseTableGsi1Name": "gsi1",
            "service": "intel-feature-registry",
            "MAX_PROFILES_PER_TEAM": "10",
            "MAX_TEAMS": "2",
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
def mock_boto3_resource(mock_table):
    dynamodb = MagicMock()
    dynamodb.Table.return_value = mock_table
    with patch("src.functions.api.register_profile.handler.boto3") as mock_boto3:
        mock_boto3.resource.return_value = dynamodb
        yield mock_boto3


@pytest.fixture
def mock_role_session():
    with patch("ncino.handler.RoleSessionCache") as mock_cache_cls:
        yield mock_cache_cls


def _create_event(body: dict) -> dict:
    return {
        "tenantArn": "arn:aws:iam::042279143912:role/TestTenant-Tenant",
        **body,
    }


class TestRegisterProfileHandler:
    def test_returns_tenant_not_found_when_no_tenant(
        self, mock_role_session, mock_boto3_resource
    ):
        from src.functions.api.register_profile.handler import handler

        mock_role_session.return_value.get_session.side_effect = Exception("no role")

        event = {"team": "marketing", "featureName": "chatbot", "modelId": "test"}
        result = handler(event, MagicMock())

        assert result["lambdaReturnCode"] == 404
        response = json.loads(result["response"])
        assert response["type"] == "not_found_error"

    def test_returns_error_when_team_missing(
        self, mock_role_session, mock_boto3_resource
    ):
        from src.functions.api.register_profile.handler import handler

        event = _create_event({"featureName": "chatbot", "modelId": "test"})
        result = handler(event, MagicMock())

        assert result["lambdaReturnCode"] == 400
        response = json.loads(result["response"])
        assert "team" in response["message"]

    def test_returns_error_when_profile_name_missing(
        self, mock_role_session, mock_boto3_resource
    ):
        from src.functions.api.register_profile.handler import handler

        event = _create_event({"team": "marketing", "modelId": "test"})
        result = handler(event, MagicMock())

        assert result["lambdaReturnCode"] == 400
        response = json.loads(result["response"])
        assert "featureName" in response["message"]

    def test_returns_error_when_model_id_missing(
        self, mock_role_session, mock_boto3_resource
    ):
        from src.functions.api.register_profile.handler import handler

        event = _create_event({"team": "marketing", "featureName": "chatbot"})
        result = handler(event, MagicMock())

        assert result["lambdaReturnCode"] == 400
        response = json.loads(result["response"])
        assert "modelId" in response["message"]

    def test_returns_provisioning_response(
        self, mock_role_session, mock_boto3_resource, mock_table
    ):
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

    def test_writes_correct_dynamo_item(
        self, mock_role_session, mock_boto3_resource, mock_table
    ):
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
        call_kwargs = mock_table.put_item.call_args[1]
        item = call_kwargs["Item"]
        assert item["pk"] == "PROFILE"
        assert (
            item["sk"]
            == "TEAM#marketing#FEATURE#chatbot#MODEL#anthropic.claude-sonnet-4-20250514"
        )
        assert item["type"] == "PROFILE"
        assert item["team"] == "marketing"
        assert item["feature_name"] == "chatbot"
        assert item["model_id"] == "anthropic.claude-sonnet-4-20250514"
        assert item["status"] == "PROVISIONING"
        assert item["gsi1pk"] == "TEAM#marketing"
        assert (
            item["gsi1sk"] == "FEATURE#chatbot#MODEL#anthropic.claude-sonnet-4-20250514"
        )
        assert item["tags"] == {"env": "demo"}
        assert isinstance(item["expires_at"], int)
        assert item["expires_at"] > int(time.time())
        assert "ConditionExpression" in call_kwargs
        assert call_kwargs["ExpressionAttributeValues"][":deleted"] == "DELETED"

    def test_rejects_duplicate_active_profile(
        self, mock_role_session, mock_boto3_resource, mock_table
    ):
        from src.functions.api.register_profile.handler import handler

        mock_table.put_item.side_effect = ClientError(
            {"Error": {"Code": "ConditionalCheckFailedException", "Message": ""}},
            "PutItem",
        )

        event = _create_event(
            {"team": "marketing", "featureName": "chatbot", "modelId": "test"}
        )
        result = handler(event, MagicMock())

        assert result["lambdaReturnCode"] == 400
        response = json.loads(result["response"])
        assert "already exists" in response["message"]

    def test_allows_reregister_after_failed(
        self, mock_role_session, mock_boto3_resource, mock_table
    ):
        from src.functions.api.register_profile.handler import handler

        event = _create_event(
            {"team": "marketing", "featureName": "chatbot", "modelId": "test"}
        )
        result = handler(event, MagicMock())

        assert result["lambdaReturnCode"] == 201
        mock_table.put_item.assert_called_once()

    def test_rejects_when_quota_exceeded(
        self, mock_role_session, mock_boto3_resource, mock_table
    ):
        from src.functions.api.register_profile.handler import handler

        active_items = [
            {"status": "ACTIVE", "feature_name": f"profile-{i}"} for i in range(10)
        ]
        mock_table.query.return_value = {"Items": active_items}

        event = _create_event(
            {"team": "marketing", "featureName": "new-profile", "modelId": "test"}
        )
        result = handler(event, MagicMock())

        assert result["lambdaReturnCode"] == 400
        response = json.loads(result["response"])
        assert "maximum" in response["message"]
        mock_table.put_item.assert_not_called()

    def test_failed_profiles_excluded_from_quota(
        self, mock_role_session, mock_boto3_resource, mock_table
    ):
        from src.functions.api.register_profile.handler import handler

        items = [
            {"status": "ACTIVE", "feature_name": f"profile-{i}"} for i in range(9)
        ] + [{"status": "FAILED", "feature_name": "failed-one"}]
        mock_table.query.return_value = {"Items": items}

        event = _create_event(
            {"team": "marketing", "featureName": "new-profile", "modelId": "test"}
        )
        result = handler(event, MagicMock())

        assert result["lambdaReturnCode"] == 201
        mock_table.put_item.assert_called_once()

    def test_quota_uses_env_var_value(
        self, mock_role_session, mock_boto3_resource, mock_table
    ):
        from src.functions.api.register_profile.handler import handler

        active_items = [
            {"status": "ACTIVE", "feature_name": f"profile-{i}"} for i in range(3)
        ]
        mock_table.query.return_value = {"Items": active_items}

        with patch.dict(os.environ, {"MAX_PROFILES_PER_TEAM": "3"}):
            event = _create_event(
                {"team": "marketing", "featureName": "new-profile", "modelId": "test"}
            )
            result = handler(event, MagicMock())

        assert result["lambdaReturnCode"] == 400
        response = json.loads(result["response"])
        assert "3" in response["message"]

    def test_allows_new_team_under_limit(
        self, mock_role_session, mock_boto3_resource, mock_table
    ):
        from src.functions.api.register_profile.handler import handler

        mock_table.query.side_effect = [
            {"Items": []},
            {"Items": [{"team": "existing-team"}]},
        ]

        event = _create_event(
            {"team": "new-team", "featureName": "chatbot", "modelId": "test"}
        )
        result = handler(event, MagicMock())

        assert result["lambdaReturnCode"] == 201
        mock_table.put_item.assert_called_once()

    def test_rejects_new_team_when_max_teams_reached(
        self, mock_role_session, mock_boto3_resource, mock_table
    ):
        from src.functions.api.register_profile.handler import handler

        existing_teams = [{"team": f"team-{i}"} for i in range(2)]
        mock_table.query.side_effect = [
            {"Items": []},
            {"Items": existing_teams},
        ]

        event = _create_event(
            {"team": "new-team", "featureName": "chatbot", "modelId": "test"}
        )
        result = handler(event, MagicMock())

        assert result["lambdaReturnCode"] == 400
        response = json.loads(result["response"])
        assert "Maximum number of teams" in response["message"]
        mock_table.put_item.assert_not_called()

    def test_allows_existing_team_when_max_teams_reached(
        self, mock_role_session, mock_boto3_resource, mock_table
    ):
        from src.functions.api.register_profile.handler import handler

        mock_table.query.return_value = {
            "Items": [{"status": "ACTIVE", "feature_name": "chatbot"}]
        }

        event = _create_event(
            {"team": "marketing", "featureName": "new-feature", "modelId": "test"}
        )
        result = handler(event, MagicMock())

        assert result["lambdaReturnCode"] == 201
        assert mock_table.query.call_count == 1

    def test_allows_existing_team_with_only_failed_profiles_when_max_teams_reached(
        self, mock_role_session, mock_boto3_resource, mock_table
    ):
        from src.functions.api.register_profile.handler import handler

        existing_teams = [{"team": f"team-{i}"} for i in range(2)] + [
            {"team": "marketing"}
        ]
        mock_table.query.side_effect = [
            {"Items": [{"status": "FAILED", "feature_name": "old"}]},
            {"Items": existing_teams},
        ]

        event = _create_event(
            {"team": "marketing", "featureName": "chatbot", "modelId": "test"}
        )
        result = handler(event, MagicMock())

        assert result["lambdaReturnCode"] == 201
        mock_table.put_item.assert_called_once()

    def test_team_limit_uses_env_var_value(
        self, mock_role_session, mock_boto3_resource, mock_table
    ):
        from src.functions.api.register_profile.handler import handler

        existing_teams = [{"team": f"team-{i}"} for i in range(5)]
        mock_table.query.side_effect = [
            {"Items": []},
            {"Items": existing_teams},
        ]

        with patch.dict(os.environ, {"MAX_TEAMS": "5"}):
            event = _create_event(
                {"team": "new-team", "featureName": "chatbot", "modelId": "test"}
            )
            result = handler(event, MagicMock())

        assert result["lambdaReturnCode"] == 400
        response = json.loads(result["response"])
        assert "5" in response["message"]

    def test_allows_reregister_after_deleted(
        self, mock_role_session, mock_boto3_resource, mock_table
    ):
        from src.functions.api.register_profile.handler import handler

        event = _create_event(
            {"team": "marketing", "featureName": "chatbot", "modelId": "test"}
        )
        result = handler(event, MagicMock())

        assert result["lambdaReturnCode"] == 201
        call_kwargs = mock_table.put_item.call_args[1]
        assert call_kwargs["ExpressionAttributeValues"][":deleted"] == "DELETED"

    def test_quota_check_paginates_through_all_pages(
        self, mock_role_session, mock_boto3_resource, mock_table
    ):
        from src.functions.api.register_profile.handler import handler

        page1 = {
            "Items": [{"status": "ACTIVE", "feature_name": f"p-{i}"} for i in range(5)],
            "LastEvaluatedKey": {"pk": "PROFILE", "sk": "TEAM#..."},
        }
        page2 = {
            "Items": [
                {"status": "ACTIVE", "feature_name": f"p-{i}"} for i in range(5, 10)
            ],
        }
        mock_table.query.side_effect = [page1, page2]

        event = _create_event(
            {"team": "marketing", "featureName": "new", "modelId": "test"}
        )
        result = handler(event, MagicMock())

        assert result["lambdaReturnCode"] == 400
        response = json.loads(result["response"])
        assert "maximum" in response["message"]
        assert mock_table.query.call_count == 2

    def test_team_count_paginates_through_all_pages(
        self, mock_role_session, mock_boto3_resource, mock_table
    ):
        from src.functions.api.register_profile.handler import handler

        quota_response = {"Items": []}
        teams_page1 = {
            "Items": [{"team": "team-0"}, {"team": "team-1"}],
            "LastEvaluatedKey": {"pk": "PROFILE", "sk": "TEAM#..."},
        }
        teams_page2 = {
            "Items": [{"team": "team-1"}],
        }
        mock_table.query.side_effect = [quota_response, teams_page1, teams_page2]

        event = _create_event(
            {"team": "new-team", "featureName": "chatbot", "modelId": "test"}
        )
        result = handler(event, MagicMock())

        assert result["lambdaReturnCode"] == 400
        response = json.loads(result["response"])
        assert "Maximum number of teams" in response["message"]
        assert mock_table.query.call_count == 3
