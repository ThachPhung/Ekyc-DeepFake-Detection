"""In-process LLM token counters since service start."""

from __future__ import annotations

from copy import deepcopy
from threading import Lock

from ekyc_document.schemas import LLMUsageSummary

_lock = Lock()
_metrics: dict[str, object] = {
    "document_requests_with_llm": 0,
    "llm_calls": 0,
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0,
    "extract_tokens": 0,
    "review_tokens": 0,
    "by_provider": {},
}


def record_llm_usage(usage: LLMUsageSummary | None) -> None:
    if usage is None or usage.call_count == 0:
        return

    with _lock:
        _metrics["document_requests_with_llm"] = int(_metrics["document_requests_with_llm"]) + 1
        _metrics["llm_calls"] = int(_metrics["llm_calls"]) + usage.call_count
        _metrics["prompt_tokens"] = int(_metrics["prompt_tokens"]) + usage.total_prompt_tokens
        _metrics["completion_tokens"] = (
            int(_metrics["completion_tokens"]) + usage.total_completion_tokens
        )
        _metrics["total_tokens"] = int(_metrics["total_tokens"]) + usage.total_tokens

        if usage.extract is not None:
            _metrics["extract_tokens"] = int(_metrics["extract_tokens"]) + usage.extract.total_tokens
            _accumulate_provider(usage.extract)
        if usage.review is not None:
            _metrics["review_tokens"] = int(_metrics["review_tokens"]) + usage.review.total_tokens
            _accumulate_provider(usage.review)


def _accumulate_provider(usage) -> None:
    provider = usage.provider or "unknown"
    by_provider = _metrics["by_provider"]
    assert isinstance(by_provider, dict)
    bucket = by_provider.setdefault(
        provider,
        {
            "llm_calls": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
    )
    bucket["llm_calls"] = int(bucket["llm_calls"]) + 1
    bucket["prompt_tokens"] = int(bucket["prompt_tokens"]) + usage.prompt_tokens
    bucket["completion_tokens"] = int(bucket["completion_tokens"]) + usage.completion_tokens
    bucket["total_tokens"] = int(bucket["total_tokens"]) + usage.total_tokens


def llm_usage_metrics() -> dict[str, object]:
    with _lock:
        return deepcopy(_metrics)
