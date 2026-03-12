import os
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
            "service": "intelligent-gateway",
        },
    ):
        yield


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
                        "pk": {"S": new_image.get("pk", "T#test#PROFILE")},
                        "sk": {"S": new_image.get("sk", "PROFILE#01HXYZ")},
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


class TestProvisionProfileHandler:
    @patch("src.functions.jobs.provision_profile.handler.boto3")
    def test_creates_inference_profile_and_updates_status(self, mock_boto3):
        mock_bedrock = MagicMock()
        mock_bedrock.create_inference_profile.return_value = {
            "inferenceProfileArn": "arn:aws:bedrock:us-east-1:042279143912:application-inference-profile/abc123"
        }

        mock_table = MagicMock()
        mock_table.get_item.return_value = {"Item": {"status": "PROVISIONING"}}
        mock_dynamodb = MagicMock()
        mock_dynamodb.Table.return_value = mock_table

        mock_boto3.client.return_value = mock_bedrock
        mock_boto3.resource.return_value = mock_dynamodb

        from src.functions.jobs.provision_profile.handler import handler

        event = _create_stream_event(
            {
                "pk": "T#test#PROFILE",
                "sk": "PROFILE#01HXYZ",
                "profile_id": "01HXYZ",
                "team": "marketing",
                "feature_name": "chatbot",
                "model_id": "anthropic.claude-sonnet-4-20250514",
                "type": "PROFILE",
                "status": "PROVISIONING",
            }
        )

        handler(event, MagicMock())

        mock_bedrock.create_inference_profile.assert_called_once()
        call_kwargs = mock_bedrock.create_inference_profile.call_args[1]
        assert call_kwargs["inferenceProfileName"].startswith("ig-marketing-chatbot-")
        assert "copyFrom" in call_kwargs["modelSource"]

        mock_table.update_item.assert_called_once()
        update_kwargs = mock_table.update_item.call_args[1]
        assert update_kwargs["ExpressionAttributeValues"][":status"] == "ACTIVE"
        assert ":arn" in update_kwargs["ExpressionAttributeValues"]

    @patch("src.functions.jobs.provision_profile.handler.boto3")
    def test_handles_bedrock_error(self, mock_boto3):
        mock_bedrock = MagicMock()
        mock_bedrock.create_inference_profile.side_effect = Exception("Quota exceeded")

        mock_table = MagicMock()
        mock_table.get_item.return_value = {"Item": {"status": "PROVISIONING"}}
        mock_dynamodb = MagicMock()
        mock_dynamodb.Table.return_value = mock_table

        mock_boto3.client.return_value = mock_bedrock
        mock_boto3.resource.return_value = mock_dynamodb

        from src.functions.jobs.provision_profile.handler import handler

        event = _create_stream_event(
            {
                "pk": "T#test#PROFILE",
                "sk": "PROFILE#01HXYZ",
                "profile_id": "01HXYZ",
                "team": "marketing",
                "feature_name": "chatbot",
                "model_id": "anthropic.claude-sonnet-4-20250514",
                "type": "PROFILE",
                "status": "PROVISIONING",
            }
        )

        handler(event, MagicMock())

        mock_table.update_item.assert_called_once()
        update_kwargs = mock_table.update_item.call_args[1]
        assert update_kwargs["ExpressionAttributeValues"][":status"] == "FAILED"
        assert "Quota exceeded" in update_kwargs["ExpressionAttributeValues"][":err"]

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
                            "pk": {"S": "T#test#PROFILE"},
                            "sk": {"S": "PROFILE#01"},
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

        event = _create_stream_event(
            {
                "pk": "T#test#PROFILE",
                "sk": "PROFILE#01HXYZ",
                "profile_id": "01HXYZ",
                "team": "marketing",
                "feature_name": "chatbot",
                "model_id": "anthropic.claude-sonnet-4-20250514",
                "type": "PROFILE",
                "status": "PROVISIONING",
            }
        )

        handler(event, MagicMock())

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

        event = _create_stream_event(
            {
                "pk": "T#test#PROFILE",
                "sk": "PROFILE#01HXYZ",
                "profile_id": "01HXYZ",
                "team": "marketing",
                "feature_name": "chatbot",
                "model_id": "anthropic.claude-sonnet-4-20250514",
                "type": "PROFILE",
                "status": "PROVISIONING",
            }
        )

        handler(event, MagicMock())

        mock_boto3.client.return_value.create_inference_profile.assert_not_called()
        mock_table.update_item.assert_not_called()
