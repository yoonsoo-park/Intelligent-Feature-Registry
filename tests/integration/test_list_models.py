import pytest


@pytest.mark.integration
class TestListModels:
    def test_returns_models_list(self, api_client):
        resp = api_client.list_models()

        assert resp.status_code == 200
        data = resp.json()
        assert "models" in data
        assert isinstance(data["models"], list)

    def test_models_have_required_fields(self, api_client):
        resp = api_client.list_models()
        models = resp.json()["models"]
        if not models:
            pytest.skip("No models available")

        required = {
            "modelId",
            "modelName",
            "providerName",
            "inputModalities",
            "outputModalities",
            "streamingSupported",
        }
        for model in models:
            assert required.issubset(model.keys()), (
                f"Missing: {required - model.keys()}"
            )

    def test_models_filtered_by_allowed_providers(self, api_client):
        resp = api_client.list_models()
        models = resp.json()["models"]
        allowed = {"Anthropic", "Amazon"}

        for model in models:
            assert model["providerName"] in allowed, (
                f"Unexpected provider: {model['providerName']}"
            )

    def test_models_sorted_by_provider_then_name(self, api_client):
        resp = api_client.list_models()
        models = resp.json()["models"]
        if len(models) < 2:
            pytest.skip("Need at least 2 models to verify sorting")

        sort_keys = [(m["providerName"], m["modelName"]) for m in models]
        assert sort_keys == sorted(sort_keys)
