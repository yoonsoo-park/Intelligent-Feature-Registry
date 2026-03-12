import json
import os
import time
import urllib.request

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

API_URL = os.environ.get("INTEL_GATEWAY_API_URL", "")
REGION = "us-east-1"


def sign_request(method, url, body=None):
    session = boto3.Session()
    credentials = session.get_credentials().get_frozen_credentials()
    headers = {"Content-Type": "application/json"}
    request = AWSRequest(method=method, url=url, data=body, headers=headers)
    SigV4Auth(credentials, "execute-api", REGION).add_auth(request)
    return dict(request.headers)


def register_profile(team, feature_name, model_id):
    url = f"{API_URL}/profiles"
    body = json.dumps(
        {
            "team": team,
            "featureName": feature_name,
            "modelId": model_id,
            "tags": {"environment": "demo"},
        }
    )
    headers = sign_request("POST", url, body)
    req = urllib.request.Request(
        url, data=body.encode(), headers=headers, method="POST"
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


def lookup_profile(team, feature_name):
    url = f"{API_URL}/profiles?team={team}&featureName={feature_name}"
    headers = sign_request("GET", url)
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


def main():
    if not API_URL:
        print("Error: Set INTEL_GATEWAY_API_URL environment variable")
        print(
            "Example: export INTEL_GATEWAY_API_URL=https://xxxxx.execute-api.us-east-1.amazonaws.com/blue"
        )
        return

    print("=== Intelligent Gateway Demo ===\n")

    print("Step 1: Register a new profile")
    result = register_profile(
        "marketing", "chatbot", "anthropic.claude-sonnet-4-20250514"
    )
    print(f"  Response: {json.dumps(result, indent=2)}")
    print(f"  Profile ID: {result['id']}")
    print(f"  Status: {result['status']}\n")

    print("Step 2: Wait for provisioning (polling every 2s)...")
    status = "PROVISIONING"
    lookup = {}
    for attempt in range(15):
        time.sleep(2)
        try:
            lookup = lookup_profile("marketing", "chatbot")
            status = lookup["status"]
            print(f"  Attempt {attempt + 1}: status={status}")
            if status in ("ACTIVE", "FAILED"):
                break
        except Exception as e:
            print(f"  Attempt {attempt + 1}: waiting... ({e})")

    if status == "ACTIVE":
        print(f"\n  Inference Profile ARN: {lookup['inferenceProfileArn']}")
        print(f"  Inference Profile ID:  {lookup['inferenceProfileId']}")

        print("\nStep 3: Use the inference profile to call Bedrock")
        bedrock_runtime = boto3.client("bedrock-runtime", region_name=REGION)
        response = bedrock_runtime.converse(
            modelId=lookup["inferenceProfileArn"],
            messages=[
                {"role": "user", "content": [{"text": "Say hello in one sentence."}]}
            ],
            inferenceConfig={"maxTokens": 100},
        )
        output_text = response["output"]["message"]["content"][0]["text"]
        print(f"  Model response: {output_text}")
    elif status == "FAILED":
        print(f"\n  Error: {lookup.get('error')}")
    else:
        print("\n  Timed out waiting for provisioning")

    print("\n=== Demo Complete ===")


if __name__ == "__main__":
    main()
