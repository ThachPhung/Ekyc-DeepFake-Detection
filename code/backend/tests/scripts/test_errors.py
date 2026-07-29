from fastapi import HTTPException, status

from app.core import errors


def test_http_error_builds_fastapi_exception() -> None:
    exc = errors.http_error(
        status.HTTP_400_BAD_REQUEST,
        {"message": "Invalid payload"},
        headers={"X-Test": "1"},
    )

    assert isinstance(exc, HTTPException)
    assert exc.status_code == status.HTTP_400_BAD_REQUEST
    assert exc.detail == {"message": "Invalid payload"}
    assert exc.headers == {"X-Test": "1"}


def test_common_error_helpers_keep_status_codes() -> None:
    assert errors.bad_request("Invalid").status_code == status.HTTP_400_BAD_REQUEST
    assert errors.unauthorized("Login required").status_code == status.HTTP_401_UNAUTHORIZED
    assert errors.forbidden("No access").status_code == status.HTTP_403_FORBIDDEN
    assert errors.not_found("Missing").status_code == status.HTTP_404_NOT_FOUND
    assert errors.conflict("Already exists").status_code == status.HTTP_409_CONFLICT
    assert (
        errors.unprocessable_entity("Invalid state").status_code
        == status.HTTP_422_UNPROCESSABLE_ENTITY
    )
    assert (
        errors.internal_server_error("Failed").status_code
        == status.HTTP_500_INTERNAL_SERVER_ERROR
    )
    assert (
        errors.service_unavailable("Try later").status_code
        == status.HTTP_503_SERVICE_UNAVAILABLE
    )
