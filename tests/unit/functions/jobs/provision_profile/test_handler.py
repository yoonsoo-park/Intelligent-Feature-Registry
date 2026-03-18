import os
import time
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def mock_env_vars():
    with patch.dict(
        os.environ,
        {
            "region": "us-east-1",
            "databaseTableName": "test-table",
            "databaseTableGsi1Name": "gsi1",
            "awsAccountId": "042279143912",
            "service": "intel-feature-registry",
        },
    ):
        yield


CRIS_ARN = "arn:aws:bedrock:us-east-1:123456789012:inference-profile/us.anthropic.claude-sonnet-4-20250514"
APP_PROFILE_ARN = (
    "arn:aws:bedrock:us-east-1:042279143912:application-inference-profile/abc123"
)
FOUNDATION_ARN = (
    "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-sonnet-4-20250514"
)

STREAM_IMAGE = {
    "pk": "PROFILE",
    "sk": "TEAM#marketing#FEATURE#chatbot#MODEL#anthropic.claude-sonnet-4-20250514",
    "profile_id": "01HXYZ",
    "team": "marketing",
    "feature_name": "chatbot",
    "model_id": "anthropic.claude-sonnet-4-20250514",
    "type": "PROFILE",
    "status": "PROVISIONING",
}


def _create_stream_event(new_image: dict) -> dict:
    return {
        "Records": [
            {
                "eventID": "1",
                "eventName": "INSERT",
                "eventVersion": "1.1",
                "eventSource": "aws:dynamodb",
                "awsRegion": "us-east-1",
                "dynamodb": {
                    "Keys": {
                        "pk": {"S": new_image.get("pk", "PROFILE")},
                        "sk": {
                            "S": new_image.get(
                                "sk",
                                "TEAM#marketing#FEATURE#chatbot#MODEL#anthropic.claude-sonnet-4-20250514",
                            )
                        },
                    },
                    "NewImage": {
                        k: {"S": str(v)}
                        if isinstance(v, str)
                        else {"M": {}}
                        if isinstance(v, dict)
                        else {"S": str(v)}
                        for k, v in new_image.items()
                    },
                    "StreamViewType": "NEW_AND_OLD_IMAGES",
                },
            }
        ]
    }


def _setup_boto3(mock_boto3, mock_bedrock, get_item_return=None):
    mock_table = MagicMock()
    mock_table.get_item.return_value = get_item_return or {
        "Item": {"status": "PROVISIONING"}
    }
    mock_dynamodb = MagicMock()
    mock_dynamodb.Table.return_value = mock_table

    mock_boto3.client.return_value = mock_bedrock
    mock_boto3.resource.return_value = mock_dynamodb
    return mock_table


class TestProvisionProfileHandler:
    @patch("src.functions.jobs.provision_profile.handler.boto3")
    def test_creates_inference_profile_with_cris_source(self, mock_boto3):
        mock_bedrock = MagicMock()
        mock_bedrock.get_inference_profile.return_value = {
            "status": "ACTIVE",
            "inferenceProfileArn": CRIS_ARN,
        }
        mock_bedrock.create_inference_profile.return_value = {
            "inferenceProfileArn": APP_PROFILE_ARN
        }
        mock_table = _setup_boto3(mock_boto3, mock_bedrock)

        from src.functions.jobs.provision_profile.handler import handler

        handler(_create_stream_event(STREAM_IMAGE), MagicMock())

        mock_bedrock.get_inference_profile.assert_called_once_with(
            inferenceProfileIdentifier="us.anthropic.claude-sonnet-4-20250514"
        )
        call_kwargs = mock_bedrock.create_inference_profile.call_args[1]
        assert call_kwargs["inferenceProfileName"].startswith(
            "ig-marketing-chatbot-claude-sonnet-4-20250514-"
        )
        assert call_kwargs["modelSource"]["copyFrom"] == CRIS_ARN

        update_kwargs = mock_table.update_item.call_args[1]
        assert update_kwargs["ExpressionAttributeValues"][":status"] == "ACTIVE"
        assert ":arn" in update_kwargs["ExpressionAttributeValues"]
        assert "REMOVE expires_at" in update_kwargs["UpdateExpression"]

    @patch("src.functions.jobs.provision_profile.handler.boto3")
    def test_falls_back_to_foundation_model_when_cris_not_found(self, mock_boto3):
        mock_bedrock = MagicMock()
        mock_bedrock.exceptions.ResourceNotFoundException = type(
            "ResourceNotFoundException", (Exception,), {}
        )
        mock_bedrock.get_inference_profile.side_effect = (
            mock_bedrock.exceptions.ResourceNotFoundException("not found")
        )
        mock_bedrock.create_inference_profile.return_value = {
            "inferenceProfileArn": APP_PROFILE_ARN
        }
        mock_table = _setup_boto3(mock_boto3, mock_bedrock)

        from src.functions.jobs.provision_profile.handler import handler

        handler(_create_stream_event(STREAM_IMAGE), MagicMock())

        call_kwargs = mock_bedrock.create_inference_profile.call_args[1]
        assert call_kwargs["modelSource"]["copyFrom"] == FOUNDATION_ARN

        update_kwargs = mock_table.update_item.call_args[1]
        assert update_kwargs["ExpressionAttributeValues"][":status"] == "ACTIVE"

    @patch("src.functions.jobs.provision_profile.handler.boto3")
    def test_handles_bedrock_error(self, mock_boto3):
        mock_bedrock = MagicMock()
        mock_bedrock.get_inference_profile.return_value = {
            "status": "ACTIVE",
            "inferenceProfileArn": CRIS_ARN,
        }
        mock_bedrock.create_inference_profile.side_effect = Exception("Quota exceeded")
        mock_table = _setup_boto3(mock_boto3, mock_bedrock)

        from src.functions.jobs.provision_profile.handler import handler

        handler(_create_stream_event(STREAM_IMAGE), MagicMock())

        update_kwargs = mock_table.update_item.call_args[1]
        assert update_kwargs["ExpressionAttributeValues"][":status"] == "FAILED"
        assert "Quota exceeded" in update_kwargs["ExpressionAttributeValues"][":err"]
        assert update_kwargs["ExpressionAttributeValues"][":ttl"] > int(time.time())

    @patch("src.functions.jobs.provision_profile.handler.boto3")
    def test_skips_records_without_new_image(self, mock_boto3):
        from src.functions.jobs.provision_profile.handler import handler

        event = {
            "Records": [
                {
                    "eventID": "1",
                    "eventName": "INSERT",
                    "eventVersion": "1.1",
                    "eventSource": "aws:dynamodb",
                    "awsRegion": "us-east-1",
                    "dynamodb": {
                        "Keys": {
                            "pk": {"S": "PROFILE"},
                            "sk": {"S": "TEAM#marketing#FEATURE#chatbot#MODEL#test"},
                        },
                        "StreamViewType": "NEW_AND_OLD_IMAGES",
                    },
                }
            ]
        }

        handler(event, MagicMock())

        mock_boto3.client.return_value.create_inference_profile.assert_not_called()

    @patch("src.functions.jobs.provision_profile.handler.boto3")
    def test_skips_provisioning_when_item_deleted(self, mock_boto3):
        mock_table = MagicMock()
        mock_table.get_item.return_value = {}
        mock_dynamodb = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_boto3.resource.return_value = mock_dynamodb

        from src.functions.jobs.provision_profile.handler import handler

        handler(_create_stream_event(STREAM_IMAGE), MagicMock())

        mock_boto3.client.return_value.create_inference_profile.assert_not_called()
        mock_table.update_item.assert_not_called()

    @patch("src.functions.jobs.provision_profile.handler.boto3")
    def test_skips_provisioning_when_status_changed(self, mock_boto3):
        mock_table = MagicMock()
        mock_table.get_item.return_value = {"Item": {"status": "FAILED"}}
        mock_dynamodb = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_boto3.resource.return_value = mock_dynamodb

        from src.functions.jobs.provision_profile.handler import handler

        handler(_create_stream_event(STREAM_IMAGE), MagicMock())

        mock_boto3.client.return_value.create_inference_profile.assert_not_called()
        mock_table.update_item.assert_not_called()

    @patch("src.functions.jobs.provision_profile.handler.boto3")
    def test_rolls_back_bedrock_profile_when_ddb_update_fails(self, mock_boto3):
        mock_bedrock = MagicMock()
        mock_bedrock.get_inference_profile.return_value = {
            "status": "ACTIVE",
            "inferenceProfileArn": CRIS_ARN,
        }
        mock_bedrock.create_inference_profile.return_value = {
            "inferenceProfileArn": APP_PROFILE_ARN
        }
        mock_table = _setup_boto3(mock_boto3, mock_bedrock)
        mock_table.update_item.side_effect = [
            Exception("DDB write failed"),
            None,
        ]

        from src.functions.jobs.provision_profile.handler import handler

        handler(_create_stream_event(STREAM_IMAGE), MagicMock())

        mock_bedrock.delete_inference_profile.assert_called_once_with(
            inferenceProfileIdentifier=APP_PROFILE_ARN
        )
        failed_update = mock_table.update_item.call_args_list[-1][1]
        assert failed_update["ExpressionAttributeValues"][":status"] == "FAILED"
