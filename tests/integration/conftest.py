import json
import os
import time
import uuid
from urllib.parse import urlencode

import boto3
import pytest
import requests
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

REGION = "us-east-1"


def _get_api_url():
    url = os.environ.get("INTEL_GATEWAY_API_URL", "")
    if not url:
        pytest.skip("INTEL_GATEWAY_API_URL not set")
    return url.rstrip("/")


class ApiClient:
    def __init__(self, base_url: str, session: boto3.Session):
        self._base_url = base_url
        self._session = session
        self._credentials = session.get_credentials().get_frozen_credentials()

    def _sign(self, method: str, url: str, body: str | None = None) -> dict:
        headers = {"Content-Type": "application/json"}
        aws_request = AWSRequest(method=method, url=url, data=body, headers=headers)
        SigV4Auth(self._credentials, "execute-api", REGION).add_auth(aws_request)
        return dict(aws_request.headers)

    def list_models(self) -> requests.Response:
        url = f"{self._base_url}/models"
        headers = self._sign("GET", url)
        return requests.get(url, headers=headers, timeout=30)

    def register_profile(
        self, team: str, feature_name: str, model_id: str, tags: dict | None = None
    ) -> requests.Response:
        url = f"{self._base_url}/profiles"
        payload = {"team": team, "featureName": feature_name, "modelId": model_id}
        if tags:
            payload["tags"] = tags
        body = json.dumps(payload)
        headers = self._sign("POST", url, body)
        return requests.post(url, data=body, headers=headers, timeout=30)

    def lookup_profile(
        self, team: str, feature_name: str, model_id: str
    ) -> requests.Response:
        params = urlencode(
            {"team": team, "featureName": feature_name, "modelId": model_id}
        )
        url = f"{self._base_url}/profiles?{params}"
        headers = self._sign("GET", url)
        return requests.get(url, headers=headers, timeout=30)

    def delete_profile(
        self, team: str, feature_name: str, model_id: str
    ) -> requests.Response:
        params = urlencode(
            {"team": team, "featureName": feature_name, "modelId": model_id}
        )
        url = f"{self._base_url}/profiles?{params}"
        headers = self._sign("DELETE", url)
        return requests.delete(url, headers=headers, timeout=30)

    def poll_until_terminal(
        self,
        team: str,
        feature_name: str,
        model_id: str,
        timeout: int = 60,
        interval: int = 2,
    ) -> requests.Response:
        deadline = time.time() + timeout
        last_response = None
        while time.time() < deadline:
            resp = self.lookup_profile(team, feature_name, model_id)
            last_response = resp
            if resp.status_code == 200:
                status = resp.json().get("status")
                if status in ("ACTIVE", "FAILED"):
                    return resp
            time.sleep(interval)
        return last_response


@pytest.fixture(scope="session")
def api_url():
    return _get_api_url()


@pytest.fixture(scope="session")
def boto_session():
    return boto3.Session()


@pytest.fixture(scope="session")
def run_id():
    return uuid.uuid4().hex[:8]


@pytest.fixture(scope="session")
def api_client(api_url, boto_session):
    return ApiClient(api_url, boto_session)


@pytest.fixture
def cleanup(api_client):
    profiles_to_delete = []

    def _register(team: str, feature_name: str, model_id: str):
        profiles_to_delete.append((team, feature_name, model_id))

    yield _register

    for team, feature_name, model_id in profiles_to_delete:
        try:
            api_client.delete_profile(team, feature_name, model_id)
        except Exception:
            pass


@pytest.fixture
def unique_team(run_id):
    return f"inttest-{run_id}"


@pytest.fixture
def unique_feature():
    return f"feat-{uuid.uuid4().hex[:6]}"
