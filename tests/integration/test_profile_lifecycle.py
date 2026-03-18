import pytest


MODEL_ID = "anthropic.claude-sonnet-4-20250514-v1:0"


@pytest.mark.integration
class TestProfileLifecycle:
    def test_full_lifecycle_register_poll_delete(
        self, api_client, cleanup, unique_team, unique_feature
    ):
        team = unique_team
        feature = unique_feature
        cleanup(team, feature, MODEL_ID)

        resp = api_client.register_profile(
            team, feature, MODEL_ID, tags={"environment": "integration-test"}
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "PROVISIONING"
        assert data["team"] == team
        assert data["featureName"] == feature
        assert data["modelId"] == MODEL_ID
        assert "id" in data
        assert "createdAt" in data
        profile_id = data["id"]

        resp = api_client.lookup_profile(team, feature, MODEL_ID)
        assert resp.status_code == 200
        assert resp.json()["status"] in ("PROVISIONING", "ACTIVE")

        resp = api_client.poll_until_terminal(team, feature, MODEL_ID, timeout=60)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ACTIVE", f"Expected ACTIVE but got {data}"
        assert "inferenceProfileArn" in data
        assert "inferenceProfileId" in data
        assert data["id"] == profile_id

        resp = api_client.delete_profile(team, feature, MODEL_ID)
        assert resp.status_code == 200
        assert resp.json()["status"] == "DELETED"

        resp = api_client.lookup_profile(team, feature, MODEL_ID)
        assert resp.status_code == 404
