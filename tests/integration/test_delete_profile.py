import pytest

MODEL_ID = "anthropic.claude-sonnet-4-20250514-v1:0"


@pytest.mark.integration
class TestDeleteProfile:
    def test_returns_404_for_nonexistent_profile(self, api_client, unique_team):
        resp = api_client.delete_profile(
            unique_team, "nonexistent-feature", "nonexistent-model"
        )
        assert resp.status_code == 404

    def test_delete_provisioning_profile(self, api_client, unique_team, unique_feature):
        team = unique_team
        feature = unique_feature

        resp = api_client.register_profile(team, feature, MODEL_ID)
        assert resp.status_code == 201

        resp = api_client.delete_profile(team, feature, MODEL_ID)
        assert resp.status_code == 200
        assert resp.json()["status"] == "DELETED"

    def test_lookup_after_delete_returns_deleted_status(
        self, api_client, unique_team, unique_feature
    ):
        team = unique_team
        feature = unique_feature

        resp = api_client.register_profile(team, feature, MODEL_ID)
        assert resp.status_code == 201

        resp = api_client.delete_profile(team, feature, MODEL_ID)
        assert resp.status_code == 200
        assert resp.json()["status"] == "DELETED"

        resp = api_client.lookup_profile(team, feature, MODEL_ID)
        assert resp.status_code == 200
        assert resp.json()["status"] == "DELETED"
