from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

import boto3

cache: dict[str, Tuple[boto3.Session, datetime]] = {}


class RoleSessionCache:
    _instance = None

    def __new__(cls, *, region_name):
        if cls._instance is None:
            cls._instance = super(RoleSessionCache, cls).__new__(cls)
        return cls._instance

    def __init__(self, *, region_name: str):
        self._sts = boto3.client(
            "sts",
            region_name=region_name,
            endpoint_url=f"https://sts.{region_name}.amazonaws.com",
        )
        self._region_name = region_name

    def get_session(
        self, role_arn: str, session_name: str = "", policy: str = ""
    ) -> boto3.Session:
        global cache

        session, expiration = cache.get(role_arn + session_name + policy, (None, None))
        if (
            session
            and expiration
            and datetime.now(tz=timezone.utc) + timedelta(minutes=5) < expiration
        ):
            return session

        session, expiration = self._assume_role(role_arn, session_name, policy)
        cache[role_arn + session_name + policy] = session, expiration
        return session

    def _assume_role(
        self,
        role_arn: str,
        session_name: str = "",
        policy: str = "",
        session: Optional[boto3.Session] = None,
    ) -> Tuple[boto3.Session, datetime]:
        role_session_name = session_name or "nCinoAwsSDK"

        client = (
            session.client(
                "sts",
                region_name=self._region_name,
                endpoint_url=f"https://sts.{self._region_name}.amazonaws.com",
            )
            if session
            else self._sts
        )
        if policy:
            assume_role_response = client.assume_role(
                RoleArn=role_arn, RoleSessionName=role_session_name, Policy=policy
            )
        else:
            assume_role_response = client.assume_role(
                RoleArn=role_arn, RoleSessionName=role_session_name
            )

        session = boto3.Session(
            aws_access_key_id=assume_role_response["Credentials"]["AccessKeyId"],
            aws_secret_access_key=assume_role_response["Credentials"][
                "SecretAccessKey"
            ],
            aws_session_token=assume_role_response["Credentials"]["SessionToken"],
            region_name=self._region_name,
        )
        return session, assume_role_response["Credentials"]["Expiration"]
