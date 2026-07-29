"""Call AI service for LLM admin review assist."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


async def request_admin_ai_review(*, unified_result: dict[str, Any]) -> dict[str, Any]:
    ai_base_url = settings.EKYC_AI_SERVICE_URL.rstrip("/")
    timeout_seconds = max(15.0, min(settings.EKYC_AI_REQUEST_TIMEOUT_SECONDS, 120.0))
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if settings.EKYC_INTERNAL_API_KEY:
        headers["X-Internal-API-Key"] = settings.EKYC_INTERNAL_API_KEY

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(
                f"{ai_base_url}/api/v1/admin/review-assist",
                json={"unified_result": unified_result},
                headers=headers,
            )
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text.strip()[:500] if exc.response is not None else str(exc)
        logger.warning("AI admin review rejected: %s", detail)
        raise RuntimeError(f"AI admin review error: {detail}") from exc
    except httpx.HTTPError as exc:
        logger.warning("AI admin review unreachable", exc_info=True)
        raise RuntimeError("AI admin review service is temporarily unavailable.") from exc

    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("AI admin review returned invalid JSON.")
    return payload
