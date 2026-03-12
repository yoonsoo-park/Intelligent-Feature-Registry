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
            "service": "intelligent-feature-registry",
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


class TestDeleteProfileHandler:
    def test_returns_tenant_not_found_when_no_tenant(self, mock_role_session):
        from src.functions.api.delete_profile.handler import handler

        mock_role_session.return_value.get_session.side_effect = Exception("no role")

        event = {"team": "marketing", "featureName": "chatbot"}
        result = handler(event, MagicMock())

        assert result["lambdaReturnCode"] == 404
        response = json.loads(result["response"])
        assert response["type"] == "not_found_error"

    def test_returns_error_when_team_missing(self, mock_role_session):
        from src.functions.api.delete_profile.handler import handler

        event = _create_event({"featureName": "chatbot"})
        result = handler(event, MagicMock())

        assert result["lambdaReturnCode"] == 400
        response = json.loads(result["response"])
        assert "team" in response["message"]

    def test_returns_error_when_profile_name_missing(self, mock_role_session):
        from src.functions.api.delete_profile.handler import handler

        event = _create_event({"team": "marketing"})
        result = handler(event, MagicMock())

        assert result["lambdaReturnCode"] == 400
        response = json.loads(result["response"])
        assert "featureName" in response["message"]

    def test_returns_not_found_when_no_profile(self, mock_role_session, mock_table):
        from src.functions.api.delete_profile.handler import handler

        mock_table.query.return_value = {"Items": []}

        event = _create_event({"team": "marketing", "featureName": "chatbot"})
        result = handler(event, MagicMock())

        assert result["lambdaReturnCode"] == 404
        response = json.loads(result["response"])
        assert "No profile found" in response["message"]

    def test_deletes_active_profile_with_bedrock_cleanup(
        self, mock_role_session, mock_table
    ):
        from src.functions.api.delete_profile.handler import handler

        mock_table.query.return_value = {
            "Items": [
                {
                    "pk": "T#TestTenant#PROFILE",
                    "sk": "PROFILE#01HXYZ",
                    "profile_id": "01HXYZ",
                    "status": "ACTIVE",
                    "inference_profile_arn": "arn:aws:bedrock:us-east-1:042279143912:application-inference-profile/abc123",
                }
            ]
        }

        mock_bedrock = MagicMock()
        with patch("boto3.client", return_value=mock_bedrock) as mock_boto3_client:
            event = _create_event({"team": "marketing", "featureName": "chatbot"})
            result = handler(event, MagicMock())

        assert result["lambdaReturnCode"] == 200
        response = json.loads(result["response"])
        assert response["status"] == "DELETED"
        assert response["id"] == "01HXYZ"
        assert response["team"] == "marketing"
        assert response["featureName"] == "chatbot"

        # Verify Bedrock delete was called
        mock_boto3_client.assert_called_once_with("bedrock", region_name="us-east-1")
        mock_bedrock.delete_inference_profile.assert_called_once_with(
            inferenceProfileIdentifier="arn:aws:bedrock:us-east-1:042279143912:application-inference-profile/abc123"
        )

        # Verify DynamoDB delete
        mock_table.delete_item.assert_called_once_with(
            Key={"pk": "T#TestTenant#PROFILE", "sk": "PROFILE#01HXYZ"}
        )

    def test_deletes_failed_profile_without_bedrock(
        self, mock_role_session, mock_table
    ):
        from src.functions.api.delete_profile.handler import handler

        mock_table.query.return_value = {
            "Items": [
                {
                    "pk": "T#TestTenant#PROFILE",
                    "sk": "PROFILE#01HXYZ",
                    "profile_id": "01HXYZ",
                    "status": "FAILED",
                    "inference_profile_arn": None,
                }
            ]
        }

        with patch("boto3.client") as mock_boto3_client:
            event = _create_event({"team": "marketing", "featureName": "chatbot"})
            result = handler(event, MagicMock())

        assert result["lambdaReturnCode"] == 200
        response = json.loads(result["response"])
        assert response["status"] == "DELETED"

        # Bedrock should NOT be called
        mock_boto3_client.assert_not_called()

        # DynamoDB delete should still happen
        mock_table.delete_item.assert_called_once_with(
            Key={"pk": "T#TestTenant#PROFILE", "sk": "PROFILE#01HXYZ"}
        )

    def test_deletes_provisioning_profile_without_bedrock(
        self, mock_role_session, mock_table
    ):
        from src.functions.api.delete_profile.handler import handler

        mock_table.query.return_value = {
            "Items": [
                {
                    "pk": "T#TestTenant#PROFILE",
                    "sk": "PROFILE#01HXYZ",
                    "profile_id": "01HXYZ",
                    "status": "PROVISIONING",
                    "inference_profile_arn": None,
                }
            ]
        }

        with patch("boto3.client") as mock_boto3_client:
            event = _create_event({"team": "marketing", "featureName": "chatbot"})
            result = handler(event, MagicMock())

        assert result["lambdaReturnCode"] == 200
        response = json.loads(result["response"])
        assert response["status"] == "DELETED"

        # Bedrock should NOT be called
        mock_boto3_client.assert_not_called()

        # DynamoDB delete should still happen
        mock_table.delete_item.assert_called_once_with(
            Key={"pk": "T#TestTenant#PROFILE", "sk": "PROFILE#01HXYZ"}
        )
