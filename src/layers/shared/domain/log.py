from enum import StrEnum, auto
from typing import Optional, Protocol

from aws_lambda_powertools import Logger


class LogLevel(StrEnum):
    DEBUG = auto()
    INFO = auto()
    WARNING = auto()
    ERROR = auto()
    CRITICAL = auto()


class ILogService(Protocol):
    def debug(self, message: Optional[str] = None, **kwargs): ...

    def info(self, message: Optional[str] = None, **kwargs): ...

    def warning(self, message: Optional[str] = None, **kwargs): ...

    def error(self, message: Optional[str] = None, **kwargs): ...

    def critical(self, message: Optional[str] = None, **kwargs): ...


class LogService(ILogService):
    def __init__(self, logger: Logger):
        self.logger = logger

    def _log(self, level: LogLevel, message: Optional[str] = None, **kwargs):
        if message is None:
            message = ""

        invalid_keys = ["service", "tenant", "orgId", "clientEnv", "userId"]
        if any(key in kwargs for key in invalid_keys):
            raise ValueError("Invalid key included in log kwargs")

        if level == LogLevel.DEBUG:
            self.logger.debug(message, **kwargs)
        elif level == LogLevel.INFO:
            self.logger.info(message, **kwargs)
        elif level == LogLevel.WARNING:
            self.logger.warning(message, **kwargs)
        elif level == LogLevel.ERROR:
            self.logger.error(message, **kwargs)
        elif level == LogLevel.CRITICAL:
            self.logger.critical(message, **kwargs)

    def debug(self, message: Optional[str] = None, **kwargs):
        self._log(LogLevel.DEBUG, message, **kwargs)

    def info(self, message: Optional[str] = None, **kwargs):
        self._log(LogLevel.INFO, message, **kwargs)

    def warning(self, message: Optional[str] = None, **kwargs):
        self._log(LogLevel.WARNING, message, **kwargs)

    def error(self, message: Optional[str] = None, **kwargs):
        self._log(LogLevel.ERROR, message, **kwargs)

    def critical(self, message: Optional[str] = None, **kwargs):
        self._log(LogLevel.CRITICAL, message, **kwargs)
