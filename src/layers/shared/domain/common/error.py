from enum import StrEnum, auto
from typing import Optional


class ErrorName(StrEnum):
    LIMIT_ERROR = auto()
    INVALID_REQUEST_ERROR = auto()
    NOT_FOUND_ERROR = auto()
    API_ERROR = auto()
    UNKNOWN_ERROR = auto()


class Error(Exception):
    def __init__(
        self,
        name: ErrorName,
        message: Optional[str] = "",
        cause: Optional[Exception] = None,
    ):
        self.name = name
        self.message = message
        self.cause = cause


class LimitError(Error):
    def __init__(self, message: str):
        super().__init__(ErrorName.LIMIT_ERROR, message)


class InvalidRequestError(Error):
    def __init__(self, message: str):
        super().__init__(ErrorName.INVALID_REQUEST_ERROR, message)


class NotFoundError(Error):
    def __init__(self, message: str):
        super().__init__(ErrorName.NOT_FOUND_ERROR, message)


class ApiError(Error):
    def __init__(self, message: str, cause: Optional[Exception] = None):
        super().__init__(ErrorName.API_ERROR, message, cause)


class UnknownError(Error):
    def __init__(self, message: str, cause: Optional[Exception] = None):
        super().__init__(ErrorName.UNKNOWN_ERROR, message, cause)
