import pytest


MODEL_ID = "anthropic.claude-sonnet-4-20250514-v1:0"


@pytest.mark.integration
class TestRegisterProfile:
    def test_rejects_duplicate_registration(
        self, api_client, cleanup, unique_team, unique_feature
    ):
        team = unique_team
        feature = unique_feature
        cleanup(team, feature, MODEL_ID)

        resp = api_client.register_profile(team, feature, MODEL_ID)
        assert resp.status_code == 201

        resp = api_client.register_profile(team, feature, MODEL_ID)
        assert resp.status_code == 400
        assert "already exists" in resp.json()["message"]

    def test_register_returns_correct_shape(
        self, api_client, cleanup, unique_team, unique_feature
    ):
        team = unique_team
        feature = unique_feature
        cleanup(team, feature, MODEL_ID)

        resp = api_client.register_profile(team, feature, MODEL_ID)
        assert resp.status_code == 201
        data = resp.json()
        required = {"id", "team", "featureName", "modelId", "status", "createdAt"}
        assert required.issubset(data.keys())
