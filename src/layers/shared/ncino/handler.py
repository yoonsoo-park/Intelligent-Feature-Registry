import json
import os
from abc import ABC, abstractmethod
from typing import Any, Callable, Optional

import boto3
from aws_lambda_powertools import Logger
from aws_lambda_powertools.logging.formatters.datadog import DatadogLogFormatter
from aws_lambda_powertools.utilities.typing import LambdaContext
from ncino.role_session import RoleSessionCache


class LambdaError(Exception):
    def __init__(
        self,
        http_status_code: int,
        message: Optional[str] = None,
        *,
        details: Optional[str] = "",
    ):
        response = {
            "code": http_status_code,
            "message": message,
            "details": details,
            "headers": {"Content-Type": "application/json"},
        }

        super().__init__(json.dumps(response))


class ALambdaHandler(ABC):
    SERVICE = os.environ.get("service", "N/A")
    LOGGER = Logger(service=SERVICE, logger_formatter=DatadogLogFormatter())

    @classmethod
    def get(cls, *args, **kwargs) -> Callable[[dict, LambdaContext], Any]:
        @ALambdaHandler.LOGGER.inject_lambda_context
        def handler(event: dict, context: LambdaContext) -> Any:
            instance = cls(*args, **kwargs)
            instance._pre_run(event)
            try:
                response = instance.main(event, context)
                return response
            except LambdaError as e:
                instance.logger.error(str(e) or "Error Message not found")
                raise e
            except Exception as e:
                instance.logger.error(e)
                raise LambdaError(500, str(e)) from e

        return handler

    def __init__(self) -> None:
        self.logger = ALambdaHandler.LOGGER
        self.profile_role_arn = ""
        self.tenant_arn = ""
        self.tenant_id = ""
        self.tenant: bool = False
        self.region_name = os.environ.get("region", "us-east-1")

    def _pre_run(self, event: dict) -> None:
        self._set_tenant(event)
        keys = {"tenant": self.tenant_id or "Unknown"}
        if "headers" in event:
            keys.update(
                {
                    "orgId": event["headers"].get("ORG_ID", "Unknown"),
                    "clientEnv": event["headers"].get("CLIENT_ENVIRONMENT", "Unknown"),
                    "userId": event["headers"].get("USER_ID")
                    or event["headers"].get("USR_ID")
                    or "Unknown",
                }
            )
        self.logger.append_keys(**keys)
        self.logger.info("PreRun")
        self.profile_role_arn = os.environ.get("featureRoleArn", "")
        if self.profile_role_arn and self.tenant_id:
            self.tenant = True

    def _set_tenant(self, event: dict) -> None:
        self.tenant_arn = event.get("tenantArn", "")
        self.auth_context = event.get("auth_context")
        if self.tenant_arn:
            self.tenant_id = self._extract_tenant_id(self.tenant_arn)
        elif self.auth_context:
            self.tenant_id = self.auth_context.get("tenantId")
        else:
            self.logger.warning(
                "Unable to set Tenant. The parameter, tenantArn, is missing from the event."
            )

    def _extract_tenant_id(self, tenant_arn: str) -> str:
        return tenant_arn.split("/")[-1].replace("-Tenant", "")

    def is_tenant_context(self) -> bool:
        return self.tenant

    def assume_profile_role(self) -> boto3.Session:
        return RoleSessionCache(region_name=self.region_name).get_session(
            self.profile_role_arn, self.tenant_id
        )

    def return_http_response(self, status_code: int, response: Any):
        return {
            "lambdaReturnCode": status_code,
            "response": json.dumps(response),
        }

    @abstractmethod
    def main(self, event: dict, context: LambdaContext) -> Any: ...
