from typing import Optional

from aws_lambda_powertools import Logger

INVALID_LOG_KEYS = {"service", "tenant", "orgId", "clientEnv", "userId"}


class LogService:
    def __init__(self, logger: Logger):
        self.logger = logger

    def _log(self, level: str, message: Optional[str] = None, **kwargs):
        if INVALID_LOG_KEYS & kwargs.keys():
            raise ValueError("Invalid key included in log kwargs")
        getattr(self.logger, level)(message or "", **kwargs)

    def debug(self, message: Optional[str] = None, **kwargs):
        self._log("debug", message, **kwargs)

    def info(self, message: Optional[str] = None, **kwargs):
        self._log("info", message, **kwargs)

    def warning(self, message: Optional[str] = None, **kwargs):
        self._log("warning", message, **kwargs)

    def error(self, message: Optional[str] = None, **kwargs):
        self._log("error", message, **kwargs)

    def critical(self, message: Optional[str] = None, **kwargs):
        self._log("critical", message, **kwargs)
