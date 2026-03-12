from functools import wraps
from typing import Optional, Tuple

from domain.common.error import Error, ErrorName
from domain.log import LogService


class RestUtil:
    @staticmethod
    def error_to_status_code(e: Error) -> int:
        match e.name:
            case ErrorName.LIMIT_ERROR | ErrorName.INVALID_REQUEST_ERROR:
                status_code = 400
            case ErrorName.NOT_FOUND_ERROR:
                status_code = 404
            case ErrorName.API_ERROR:
                status_code = 500
            case ErrorName.UNKNOWN_ERROR:
                status_code = 500
        return status_code

    @staticmethod
    def error_to_response(e: Error, message: Optional[str] = None) -> Tuple[int, dict]:
        return RestUtil.error_to_status_code(e), {
            "type": e.name.lower(),
            "message": e.message if not message else message,
        }

    @staticmethod
    def unknown_error_response() -> Tuple[int, dict]:
        return 500, {"type": "api_error", "message": "An unknown error occurred"}

    @staticmethod
    def tenant_not_found_response() -> Tuple[int, dict]:
        return 404, {
            "type": "not_found_error",
            "message": "Tenant not found",
        }

    @staticmethod
    def handle_errors(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            log_service = LogService(logger=self.logger)
            try:
                return func(self, *args, **kwargs)
            except Error as e:
                log_service.error(str(e))
                return self.return_http_response(*RestUtil.error_to_response(e))
            except Exception as e:
                log_service.error(str(e))
                return self.return_http_response(*RestUtil.unknown_error_response())

        return wrapper
