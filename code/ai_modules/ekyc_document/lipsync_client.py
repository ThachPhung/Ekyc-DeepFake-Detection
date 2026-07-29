"""HTTP client for the SyncNet lip-sync deepfake microservice (:8002)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class LipSyncServiceError(Exception):
    """Raised when the lip-sync microservice cannot be reached or returns an error."""


@dataclass(frozen=True)
class LipSyncServiceResponse:
    verdict: str
    is_fake: bool
    is_real: bool
    confidence: float
    manipulation_probability: float
    detail: str | None = None
    raw: dict[str, Any] | None = None


def request_lipsync_analysis(
    *,
    base_url: str,
    video_bytes: bytes,
    timeout_seconds: float = 120.0,
    filename: str = "ekyc_video.webm",
    content_type: str = "video/webm",
) -> LipSyncServiceResponse:
    url = f"{base_url.rstrip('/')}/api/lip-sync"
    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.post(
                url,
                files={"video_file": (filename, video_bytes, content_type)},
            )
    except httpx.TimeoutException as exc:
        raise LipSyncServiceError(
            f"Lip-sync service timeout after {timeout_seconds:.0f}s"
        ) from exc
    except httpx.RequestError as exc:
        raise LipSyncServiceError(f"Lip-sync service unreachable: {exc}") from exc

    if response.status_code == 503:
        detail = _extract_error_detail(response)
        raise LipSyncServiceError(
            detail or (
                "Lip-sync model chưa sẵn sàng (503). "
                "Kiểm tra weights SyncNet (docker compose -f compose.ai.yml up lipsync-deepfake)."
            )
        )
    if response.status_code >= 400:
        detail = _extract_error_detail(response)
        raise LipSyncServiceError(
            detail or f"Lip-sync service error HTTP {response.status_code}"
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise LipSyncServiceError("Lip-sync service returned invalid JSON") from exc

    return LipSyncServiceResponse(
        verdict=str(payload.get("verdict", "uncertain")),
        is_fake=bool(payload.get("is_fake", False)),
        is_real=bool(payload.get("is_real", False)),
        confidence=float(payload.get("confidence", 0.0)),
        manipulation_probability=float(payload.get("manipulation_probability", 0.0)),
        detail=payload.get("detail"),
        raw=payload,
    )


def probe_lipsync_service(
    *,
    base_url: str,
    timeout_seconds: float = 5.0,
) -> dict[str, object]:
    url = f"{base_url.rstrip('/')}/"
    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.get(url)
        reachable = response.status_code < 500
        payload = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        return {
            "url": base_url,
            "reachable": reachable,
            "status_code": response.status_code,
            "service": payload.get("service"),
        }
    except httpx.HTTPError as exc:
        return {
            "url": base_url,
            "reachable": False,
            "error": str(exc),
        }


def _extract_error_detail(response: httpx.Response) -> str | None:
    try:
        payload = response.json()
    except ValueError:
        text = response.text.strip()
        return text[:500] if text else None
    if isinstance(payload, dict):
        detail = payload.get("detail")
        if isinstance(detail, str):
            return detail
        if detail is not None:
            return str(detail)
    return None
