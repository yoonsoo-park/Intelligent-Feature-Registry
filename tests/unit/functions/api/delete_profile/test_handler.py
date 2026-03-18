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
            "service": "intel-feature-registry",
        },
    ):
        yield


@pytest.fixture
def mock_table():
    table = MagicMock()
    return table


@pytest.fixture
def mock_boto3_resource(mock_table):
    dynamodb = MagicMock()
    dynamodb.Table.return_value = mock_table
    with patch("src.functions.api.delete_profile.handler.boto3") as mock_boto3:
        mock_boto3.resource.return_value = dynamodb
        yield mock_boto3


@pytest.fixture
def mock_role_session():
    with patch("ncino.handler.RoleSessionCache") as mock_cache_cls:
        yield mock_cache_cls


def _create_event(params: dict) -> dict:
    return {
        "tenantArn": "arn:aws:iam::042279143912:role/TestTenant-Tenant",
        **params,
    }


class TestDeleteProfileHandler:
    def test_returns_tenant_not_found_when_no_tenant(
        self, mock_role_session, mock_boto3_resource
    ):
        from src.functions.api.delete_profile.handler import handler

        mock_role_session.return_value.get_session.side_effect = Exception("no role")

        event = {"team": "marketing", "featureName": "chatbot", "modelId": "test"}
        result = handler(event, MagicMock())

        assert result["lambdaReturnCode"] == 404
        response = json.loads(result["response"])
        assert response["type"] == "not_found_error"

    def test_returns_error_when_team_missing(
        self, mock_role_session, mock_boto3_resource
    ):
        from src.functions.api.delete_profile.handler import handler

        event = _create_event({"featureName": "chatbot", "modelId": "test"})
        result = handler(event, MagicMock())

        assert result["lambdaReturnCode"] == 400
        response = json.loads(result["response"])
        assert "team" in response["message"]

    def test_returns_error_when_profile_name_missing(
        self, mock_role_session, mock_boto3_resource
    ):
        from src.functions.api.delete_profile.handler import handler

        event = _create_event({"team": "marketing", "modelId": "test"})
        result = handler(event, MagicMock())

        assert result["lambdaReturnCode"] == 400
        response = json.loads(result["response"])
        assert "featureName" in response["message"]

    def test_returns_error_when_model_id_missing(
        self, mock_role_session, mock_boto3_resource
    ):
        from src.functions.api.delete_profile.handler import handler

        event = _create_event({"team": "marketing", "featureName": "chatbot"})
        result = handler(event, MagicMock())

        assert result["lambdaReturnCode"] == 400
        response = json.loads(result["response"])
        assert "modelId" in response["message"]

    def test_returns_not_found_when_no_profile(
        self, mock_role_session, mock_boto3_resource, mock_table
    ):
        from src.functions.api.delete_profile.handler import handler

        mock_table.get_item.return_value = {}

        event = _create_event(
            {
                "team": "marketing",
                "featureName": "chatbot",
                "modelId": "anthropic.claude-sonnet-4-20250514",
            }
        )
        result = handler(event, MagicMock())

        assert result["lambdaReturnCode"] == 404
        response = json.loads(result["response"])
        assert "No profile found" in response["message"]

    def test_deletes_active_profile_with_bedrock_cleanup(
        self, mock_role_session, mock_boto3_resource, mock_table
    ):
        from src.functions.api.delete_profile.handler import handler

        mock_table.get_item.return_value = {
            "Item": {
                "pk": "PROFILE",
                "sk": "TEAM#marketing#FEATURE#chatbot#MODEL#anthropic.claude-sonnet-4-20250514",
                "profile_id": "01HXYZ",
                "status": "ACTIVE",
                "inference_profile_arn": "arn:aws:bedrock:us-east-1:042279143912:application-inference-profile/abc123",
            }
        }

        mock_bedrock = MagicMock()
        mock_boto3_resource.client.return_value = mock_bedrock
        event = _create_event(
            {
                "team": "marketing",
                "featureName": "chatbot",
                "modelId": "anthropic.claude-sonnet-4-20250514",
            }
        )
        result = handler(event, MagicMock())

        assert result["lambdaReturnCode"] == 200
        response = json.loads(result["response"])
        assert response["status"] == "DELETED"
        assert response["id"] == "01HXYZ"
        assert response["team"] == "marketing"
        assert response["featureName"] == "chatbot"
        assert response["modelId"] == "anthropic.claude-sonnet-4-20250514"

        mock_bedrock.delete_inference_profile.assert_called_once_with(
            inferenceProfileIdentifier="arn:aws:bedrock:us-east-1:042279143912:application-inference-profile/abc123"
        )

        mock_table.delete_item.assert_called_once_with(
            Key={
                "pk": "PROFILE",
                "sk": "TEAM#marketing#FEATURE#chatbot#MODEL#anthropic.claude-sonnet-4-20250514",
            }
        )

    @pytest.mark.parametrize("status", ["FAILED", "PROVISIONING"])
    def test_deletes_non_active_profile_without_bedrock(
        self, mock_role_session, mock_boto3_resource, mock_table, status
    ):
        from src.functions.api.delete_profile.handler import handler

        mock_table.get_item.return_value = {
            "Item": {
                "pk": "PROFILE",
                "sk": "TEAM#marketing#FEATURE#chatbot#MODEL#test",
                "profile_id": "01HXYZ",
                "status": status,
                "inference_profile_arn": None,
            }
        }

        event = _create_event(
            {"team": "marketing", "featureName": "chatbot", "modelId": "test"}
        )
        result = handler(event, MagicMock())

        assert result["lambdaReturnCode"] == 200
        response = json.loads(result["response"])
        assert response["status"] == "DELETED"

        mock_table.delete_item.assert_called_once_with(
            Key={
                "pk": "PROFILE",
                "sk": "TEAM#marketing#FEATURE#chatbot#MODEL#test",
            }
        )
