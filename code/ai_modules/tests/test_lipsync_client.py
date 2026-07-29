from __future__ import annotations

from unittest.mock import patch

import pytest

from ekyc_document.lipsync_client import (
    LipSyncServiceError,
    LipSyncServiceResponse,
    request_lipsync_analysis,
)


def test_request_lipsync_analysis_parses_success_response() -> None:
    payload = {
        "verdict": "fake",
        "is_fake": True,
        "is_real": False,
        "confidence": 0.12,
        "manipulation_probability": 0.88,
        "detail": "test",
    }

    class _FakeResponse:
        status_code = 200

        @staticmethod
        def json() -> dict[str, object]:
            return payload

    class _FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def post(self, url: str, files: dict) -> _FakeResponse:
            assert url.endswith("/api/lip-sync")
            assert "video_file" in files
            return _FakeResponse()

    with patch("ekyc_document.lipsync_client.httpx.Client", return_value=_FakeClient()):
        result = request_lipsync_analysis(
            base_url="http://lipsync-deepfake:8002",
            video_bytes=b"fake-video",
        )

    assert isinstance(result, LipSyncServiceResponse)
    assert result.verdict == "fake"
    assert result.is_fake is True
    assert result.manipulation_probability == 0.88


def test_request_lipsync_analysis_raises_on_503() -> None:
    class _FakeResponse:
        status_code = 503
        text = "model missing"

        @staticmethod
        def json() -> dict[str, str]:
            return {"detail": "Model not loaded"}

    class _FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def post(self, url: str, files: dict) -> _FakeResponse:
            return _FakeResponse()

    with patch("ekyc_document.lipsync_client.httpx.Client", return_value=_FakeClient()):
        with pytest.raises(LipSyncServiceError, match="Model not loaded"):
            request_lipsync_analysis(
                base_url="http://lipsync-deepfake:8002",
                video_bytes=b"fake-video",
            )
