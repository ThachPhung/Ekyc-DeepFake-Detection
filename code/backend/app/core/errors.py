from typing import Any

from fastapi import HTTPException, status


def http_error(
    status_code: int,
    detail: Any,
    headers: dict[str, str] | None = None,
) -> HTTPException:
    return HTTPException(status_code=status_code, detail=detail, headers=headers)


def bad_request(detail: Any = "Bad request") -> HTTPException:
    return http_error(status.HTTP_400_BAD_REQUEST, detail)


def unauthorized(
    detail: Any = "Not authenticated",
    headers: dict[str, str] | None = None,
) -> HTTPException:
    return http_error(status.HTTP_401_UNAUTHORIZED, detail, headers=headers)


def forbidden(detail: Any = "Not enough permissions") -> HTTPException:
    return http_error(status.HTTP_403_FORBIDDEN, detail)


def not_found(detail: Any = "Resource not found") -> HTTPException:
    return http_error(status.HTTP_404_NOT_FOUND, detail)


def conflict(detail: Any = "Conflict") -> HTTPException:
    return http_error(status.HTTP_409_CONFLICT, detail)


def unprocessable_entity(detail: Any = "Unprocessable entity") -> HTTPException:
    return http_error(status.HTTP_422_UNPROCESSABLE_ENTITY, detail)


def internal_server_error(detail: Any = "Internal server error") -> HTTPException:
    return http_error(status.HTTP_500_INTERNAL_SERVER_ERROR, detail)


def service_unavailable(detail: Any = "Service unavailable") -> HTTPException:
    return http_error(status.HTTP_503_SERVICE_UNAVAILABLE, detail)
