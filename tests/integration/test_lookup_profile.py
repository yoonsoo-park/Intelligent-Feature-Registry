import pytest


@pytest.mark.integration
class TestLookupProfile:
    def test_returns_404_for_nonexistent_profile(self, api_client, unique_team):
        resp = api_client.lookup_profile(
            unique_team, "nonexistent-feature", "nonexistent-model"
        )
        assert resp.status_code == 404
