import os
from dataclasses import dataclass

import pytest
from fastapi import HTTPException

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("PROJECT_NAME", "Test")
os.environ.setdefault("POSTGRES_SERVER", "localhost")
os.environ.setdefault("POSTGRES_USER", "postgres")
os.environ.setdefault("FIRST_SUPERUSER", "admin@example.com")
os.environ.setdefault("FIRST_SUPERUSER_PASSWORD", "test-password")

from app.api.routes.ekyc_requests import _validate_video_metadata


@dataclass
class DummyUploadFile:
    filename: str
    content_type: str


def test_validate_video_metadata_accepts_mp4() -> None:
    file = DummyUploadFile(filename="liveness.mp4", content_type="video/mp4")

    assert _validate_video_metadata(file) == ".mp4"  # type: ignore[arg-type]


def test_validate_video_metadata_accepts_mp4_with_codec_parameter() -> None:
    file = DummyUploadFile(
        filename="liveness.mp4",
        content_type="video/mp4;codecs=avc1.42E01E",
    )

    assert _validate_video_metadata(file) == ".mp4"  # type: ignore[arg-type]


def test_validate_video_metadata_rejects_webm() -> None:
    file = DummyUploadFile(filename="liveness.webm", content_type="video/webm")

    with pytest.raises(HTTPException) as exc_info:
        _validate_video_metadata(file)  # type: ignore[arg-type]

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "The face verification video must be an MP4 file."


def test_validate_video_metadata_rejects_non_mp4_content_type() -> None:
    file = DummyUploadFile(filename="liveness.mp4", content_type="video/webm")

    with pytest.raises(HTTPException) as exc_info:
        _validate_video_metadata(file)  # type: ignore[arg-type]

    assert exc_info.value.status_code == 400
    assert (
        exc_info.value.detail
        == "The face verification video must use video/mp4 content type."
    )
