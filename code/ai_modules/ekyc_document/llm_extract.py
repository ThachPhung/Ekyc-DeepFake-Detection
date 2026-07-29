"""LLM text extraction: OCR raw text → structured fields, with optional holistic review pass."""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Literal
from urllib import error, request

from ekyc_document.config import PipelineConfig
from ekyc_document.layout_field_parse import get_ocr_locked_fields
from ekyc_document.parser import _looks_like_person_name
from ekyc_document.schemas import DocumentType, LLMTokenUsage, LLMUsageSummary, ParsedFields

_DATE_PATTERN = re.compile(r"^\d{2}[/.-]\d{2}[/.-]\d{4}$")
_CCCD_ID_PATTERN = re.compile(r"^\d{12}$")

_OCR_LOCKED_DATE_FIELDS = frozenset({"date_of_birth", "issue_date", "expiry_date"})

_EXTRACTABLE_FIELDS = (
    "id_number",
    "full_name",
    "date_of_birth",
    "sex",
    "nationality",
    "place_of_origin",
    "place_of_residence",
    "issue_date",
    "issue_place",
    "expiry_date",
)

_SYSTEM_PROMPT = """You extract structured data from noisy OCR text of Vietnamese identity documents (CCCD chip card).
Return ONLY one JSON object. No markdown, no commentary.
Use null for unknown fields. Dates must be DD/MM/YYYY.
nationality is usually "Việt Nam" when present.
Fix Vietnamese diacritics and administrative place names using context, but never invent values absent from OCR.
sex must be "Nam" or "Nữ" when known.
issue_place for CCCD back is usually "Cục Cảnh sát quản lý hành chính về trật tự xã hội".
When OCR contains [MAT_TRUOC] and [MAT_SAU], use front for identity/residence/expiry when [EXPIRY_DATE] appears on front (CCCD cũ); otherwise take expiry from back MRZ. Back supplies issue_date and issue_place only when front/back belong to the same card.
Never put English administrative boilerplate (e.g. "FOR ADMINISTRATIVE MANAGEMENT") into Vietnamese address fields.

CRITICAL — YOLO layout field blocks (mandatory source mapping):
OCR contains labeled blocks from YOLO object detection. Each field MUST come ONLY from its matching block:
- id_number ← [ID_NUMBER]
- full_name ← [FULL_NAME]
- date_of_birth ← [DATE_OF_BIRTH]
- sex ← [SEX] or [GENDER]
- nationality ← [NATIONALITY]
- place_of_origin ← [PLACE_OF_ORIGIN] or [BIRTHPLACE]
- place_of_residence ← [PLACE_OF_RESIDENCE] or [ADDRESS]
- issue_date ← [ISSUE_DATE] (usually MAT_SAU / back)
- issue_place ← [ISSUE_PLACE] (usually MAT_SAU / back)
- expiry_date ← [EXPIRY_DATE] or [EXPIRY] on MAT_TRUOC, otherwise [MRZ] on MAT_SAU
Read each [BLOCK] carefully; extract ONLY the value inside that block. Never copy values across blocks.
If a block is missing or unreadable, return null — do not guess from other blocks or other fields on the card.
Never swap birth/issue/expiry dates.

JSON keys: id_number, full_name, date_of_birth, sex, nationality, place_of_origin, place_of_residence, issue_date, issue_place, expiry_date"""

_REVIEW_SYSTEM_PROMPT = """You are a senior reviewer for Vietnamese identity document (CCCD) data extraction.
You receive noisy OCR text plus a draft JSON merged from OCR and an initial extractor.
Review ALL fields holistically against the OCR text and return the most accurate final JSON.
Rules:
- Return ONLY one JSON object. No markdown, no commentary.
- Prefer correct Vietnamese diacritics, proper administrative place names, and natural person-name casing.
- Resolve conflicts between draft fields using OCR context; never invent values absent from OCR.
- Dates must be DD/MM/YYYY. sex must be exactly "Nam" or "Nữ" (never "N", "Nu", "Female").
- Keep id_number exactly 12 digits when present in OCR.
- issue_place for CCCD must be exactly: "Cục Cảnh sát quản lý hành chính về trật tự xã hội" when issuing authority appears in OCR.
- When OCR contains [MAT_TRUOC] and [MAT_SAU], keep front-side identity/residence separate from back-side issue fields. Prefer [EXPIRY_DATE] on MAT_TRUOC when present; otherwise use MRZ expiry on MAT_SAU.
- Never copy English administrative boilerplate into place_of_origin or place_of_residence.
- Fix apostrophe OCR artifacts in names (PHU'ONG → Phương, DU'ONG → Dương).
- Remove duplicated address segments and OCR label noise.

CRITICAL — do NOT change values already confirmed from YOLO layout blocks:
Each JSON field must match its [BLOCK] in OCR. Never move values between blocks.
If draft field matches its YOLO block, keep it unchanged — especially all date fields and id_number.

JSON keys: id_number, full_name, date_of_birth, sex, nationality, place_of_origin, place_of_residence, issue_date, issue_place, expiry_date"""

_ENV_TO_CONFIG_ATTR: dict[str, str] = {
    "OPENAI_API_KEY": "openai_api_key",
    "DEEPSEEK_API_KEY": "deepseek_api_key",
    "GEMINI_API_KEY": "gemini_api_key",
    "GOOGLE_API_KEY": "google_api_key",
    "ANTHROPIC_API_KEY": "anthropic_api_key",
    "EKYC_LLM_API_KEY": "llm_api_key",
}


@dataclass(frozen=True)
class LLMProviderSpec:
    name: str
    api_style: str
    api_key_env_vars: tuple[str, ...]
    default_base_url: str | None
    default_model: str
    supports_openai_json_mode: bool = False


LLM_PROVIDERS: dict[str, LLMProviderSpec] = {
    "openai": LLMProviderSpec(
        name="openai",
        api_style="openai_chat",
        api_key_env_vars=("OPENAI_API_KEY", "EKYC_LLM_API_KEY"),
        default_base_url="https://api.openai.com/v1",
        default_model="gpt-5.4-mini",
        supports_openai_json_mode=True,
    ),
    "deepseek": LLMProviderSpec(
        name="deepseek",
        api_style="openai_chat",
        api_key_env_vars=("DEEPSEEK_API_KEY", "EKYC_LLM_API_KEY"),
        default_base_url="https://api.deepseek.com/v1",
        default_model="deepseek-chat",
        supports_openai_json_mode=True,
    ),
    "gemini": LLMProviderSpec(
        name="gemini",
        api_style="gemini",
        api_key_env_vars=("GEMINI_API_KEY", "GOOGLE_API_KEY", "EKYC_LLM_API_KEY"),
        default_base_url=None,
        default_model="gemini-2.0-flash",
        supports_openai_json_mode=False,
    ),
    "anthropic": LLMProviderSpec(
        name="anthropic",
        api_style="anthropic",
        api_key_env_vars=("ANTHROPIC_API_KEY", "EKYC_LLM_API_KEY"),
        default_base_url=None,
        default_model="claude-sonnet-4-20250514",
        supports_openai_json_mode=False,
    ),
}

_DEFAULT_MODEL_PROVIDER = {
    spec.default_model: provider for provider, spec in LLM_PROVIDERS.items()
}


@dataclass
class LLMCallResult:
    payload: dict[str, Any]
    usage: LLMTokenUsage


@dataclass
class LLMExtractResult:
    fields: ParsedFields | None
    used: bool
    reviewed: bool = False
    provider: str | None = None
    model: str | None = None
    error: str | None = None
    usage: LLMUsageSummary | None = None


class LLMFieldExtractor:
    def __init__(self, config: PipelineConfig | None = None) -> None:
        self.config = config or PipelineConfig()

    @property
    def provider_spec(self) -> LLMProviderSpec:
        provider = self.config.llm_provider.lower()
        if provider not in LLM_PROVIDERS:
            supported = ", ".join(sorted(LLM_PROVIDERS))
            raise ValueError(
                f"LLM provider '{provider}' không được hỗ trợ. "
                f"Chọn một trong: {supported}"
            )
        return LLM_PROVIDERS[provider]

    @property
    def active_model(self) -> str:
        if self.config.llm_model:
            configured_owner = _DEFAULT_MODEL_PROVIDER.get(self.config.llm_model)
            if configured_owner and configured_owner != self.provider_spec.name:
                return self.provider_spec.default_model
            return self.config.llm_model
        return self.provider_spec.default_model

    def diagnostics(self) -> dict[str, object]:
        active = self.config.llm_provider.lower()
        providers: dict[str, object] = {}
        for name, spec in LLM_PROVIDERS.items():
            key_env = _provider_configured_env(spec, self.config)
            providers[name] = {
                "default_model": spec.default_model,
                "api_key_env": key_env,
                "configured": key_env is not None,
                "active": name == active,
            }
        return {
            "enabled": self.config.llm_extract_enabled,
            "mode": self.config.llm_extract_mode,
            "review_enabled": self.config.llm_review_enabled,
            "provider": active,
            "model": self.active_model,
            "ready": self.is_ready(),
            "fallback_min_ocr_confidence": self.config.llm_fallback_min_ocr_confidence,
            "providers": providers,
        }

    def is_ready(self) -> bool:
        if not self.config.llm_extract_enabled:
            return False
        try:
            return bool(self._resolve_api_key())
        except (ValueError, RuntimeError):
            return False

    def should_run(self) -> bool:
        """LLM is the primary text extractor whenever enabled and configured."""
        return self.is_ready()

    def extract(
        self,
        raw_ocr_text: str,
        *,
        document_type: DocumentType = "CCCD",
        fallback_fields: ParsedFields | None = None,
        ocr_confidence: float = 1.0,
        rule_fields: ParsedFields | None = None,
        timings_ms: dict[str, float] | None = None,
    ) -> LLMExtractResult:
        if rule_fields is not None and fallback_fields is None:
            fallback_fields = rule_fields

        if not self.should_run():
            return LLMExtractResult(fields=None, used=False)

        if not raw_ocr_text.strip():
            return LLMExtractResult(
                fields=fallback_fields,
                used=False,
                error="empty OCR text",
            )

        provider = self.config.llm_provider.lower()
        model = self.active_model
        try:
            extract_started = time.perf_counter()
            extract_call = self._call_llm(
                raw_ocr_text,
                document_type=document_type,
                system_prompt=_SYSTEM_PROMPT,
                user_prompt=self._build_extract_user_prompt(raw_ocr_text, document_type=document_type),
                stage="extract",
            )
            if timings_ms is not None:
                timings_ms["llm_extract"] = round((time.perf_counter() - extract_started) * 1000.0, 2)
            llm_fields = _parse_llm_payload(extract_call.payload)
            ocr_locked = get_ocr_locked_fields(rule_fields)
            merged_fields = merge_rule_and_llm_fields(
                rule_fields or ParsedFields(),
                llm_fields,
                ocr_locked=ocr_locked,
            )

            reviewed = False
            final_fields = merged_fields
            review_usage: LLMTokenUsage | None = None
            if self.config.llm_review_enabled:
                review_started = time.perf_counter()
                review_call = self._call_llm(
                    raw_ocr_text,
                    document_type=document_type,
                    system_prompt=_REVIEW_SYSTEM_PROMPT,
                    user_prompt=self._build_review_user_prompt(
                        raw_ocr_text,
                        document_type=document_type,
                        draft_fields=merged_fields,
                    ),
                    stage="review",
                )
                if timings_ms is not None:
                    timings_ms["llm_review"] = round((time.perf_counter() - review_started) * 1000.0, 2)
                reviewed_fields = _parse_llm_payload(review_call.payload)
                final_fields = _finalize_reviewed_fields(
                    merged_fields,
                    reviewed_fields,
                    ocr_locked=ocr_locked,
                )
                review_usage = review_call.usage
                reviewed = True
            elif timings_ms is not None:
                timings_ms["llm_review"] = 0.0

            usage = LLMUsageSummary.from_calls(extract_call.usage, review_usage)
            return LLMExtractResult(
                fields=final_fields,
                used=True,
                reviewed=reviewed,
                provider=provider,
                model=model,
                usage=usage,
            )
        except Exception as exc:  # noqa: BLE001 — surface as warning, keep fallback
            return LLMExtractResult(
                fields=fallback_fields,
                used=False,
                provider=provider,
                model=model,
                error=str(exc),
            )

    def _resolve_api_key(self) -> str | None:
        spec = self.provider_spec
        for env_name in spec.api_key_env_vars:
            attr = _ENV_TO_CONFIG_ATTR.get(env_name)
            if attr:
                config_value = getattr(self.config, attr, None)
                if config_value and str(config_value).strip():
                    return str(config_value).strip()
            env_value = _read_env_key(env_name)
            if env_value:
                return env_value
        expected = " hoặc ".join(spec.api_key_env_vars)
        raise RuntimeError(
            f"Chưa cấu hình API key cho provider '{spec.name}'. "
            f"Đặt biến môi trường: {expected}"
        )

    def _resolve_base_url(self) -> str:
        if self.config.llm_base_url:
            return self.config.llm_base_url.rstrip("/")
        spec = self.provider_spec
        if spec.default_base_url:
            return spec.default_base_url.rstrip("/")
        raise RuntimeError(
            f"Provider '{spec.name}' cần EKYC_LLM_BASE_URL nếu không dùng endpoint mặc định."
        )

    def _build_extract_user_prompt(self, raw_ocr_text: str, *, document_type: DocumentType) -> str:
        return (
            f"Document type: {document_type}\n\n"
            f"OCR TEXT:\n{raw_ocr_text.strip()}\n\n"
            "Each [FIELD_NAME] block is a YOLO-detected region with a fixed mapping. "
            "Extract each JSON field ONLY from its matching block "
            "([ID_NUMBER], [FULL_NAME], [DATE_OF_BIRTH], [SEX], [NATIONALITY], "
            "[PLACE_OF_ORIGIN], [PLACE_OF_RESIDENCE], [ISSUE_DATE], [ISSUE_PLACE], [EXPIRY_DATE]). "
            "Return JSON only."
        )

    def _build_review_user_prompt(
        self,
        raw_ocr_text: str,
        *,
        document_type: DocumentType,
        draft_fields: ParsedFields,
    ) -> str:
        draft_json = json.dumps(
            draft_fields.model_dump(include=set(_EXTRACTABLE_FIELDS)),
            ensure_ascii=False,
            indent=2,
        )
        return (
            f"Document type: {document_type}\n\n"
            f"OCR TEXT:\n{raw_ocr_text.strip()}\n\n"
            f"DRAFT JSON (merged OCR + initial extraction):\n{draft_json}\n\n"
            "Review holistically. Do NOT change any field already matching its YOLO [BLOCK] in OCR. "
            "Return the most accurate final JSON only."
        )

    def _call_llm(
        self,
        raw_ocr_text: str,
        *,
        document_type: DocumentType,
        system_prompt: str,
        user_prompt: str | None = None,
        stage: Literal["extract", "review", "admin_review"] = "extract",
    ) -> LLMCallResult:
        prompt = user_prompt or self._build_extract_user_prompt(raw_ocr_text, document_type=document_type)
        spec = self.provider_spec
        if spec.api_style == "anthropic":
            return self._call_anthropic(prompt, system_prompt=system_prompt, stage=stage)
        if spec.api_style == "gemini":
            return self._call_gemini(prompt, system_prompt=system_prompt, stage=stage)
        return self._call_openai_compatible(prompt, system_prompt=system_prompt, stage=stage)

    def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        stage: Literal["extract", "review", "admin_review"] = "admin_review",
    ) -> LLMCallResult:
        """Structured JSON completion for non-OCR LLM tasks (e.g. admin review assist)."""
        return self._call_llm(
            "",
            document_type="CCCD",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            stage=stage,
        )

    def _call_openai_compatible(
        self,
        user_prompt: str,
        *,
        system_prompt: str,
        stage: Literal["extract", "review", "admin_review"],
    ) -> LLMCallResult:
        api_key = self._resolve_api_key()
        spec = self.provider_spec
        url = f"{self._resolve_base_url()}/chat/completions"
        body: dict[str, Any] = {
            "model": self.active_model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if spec.supports_openai_json_mode:
            body["response_format"] = {"type": "json_object"}

        raw = self._post_json(
            url,
            body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        content = raw["choices"][0]["message"]["content"]
        usage = _parse_openai_usage(
            raw,
            provider=self.config.llm_provider.lower(),
            model=self.active_model,
            stage=stage,
        )
        return LLMCallResult(payload=_loads_json_object(content), usage=usage)

    def _call_anthropic(
        self,
        user_prompt: str,
        *,
        system_prompt: str,
        stage: Literal["extract", "review", "admin_review"],
    ) -> LLMCallResult:
        api_key = self._resolve_api_key()
        url = "https://api.anthropic.com/v1/messages"
        body = {
            "model": self.active_model,
            "max_tokens": 1024,
            "temperature": 0,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }
        raw = self._post_json(
            url,
            body,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
        )
        blocks = raw.get("content") or []
        text = "".join(block.get("text", "") for block in blocks if block.get("type") == "text")
        usage = _parse_anthropic_usage(
            raw,
            provider=self.config.llm_provider.lower(),
            model=self.active_model,
            stage=stage,
        )
        return LLMCallResult(payload=_loads_json_object(text), usage=usage)

    def _call_gemini(
        self,
        user_prompt: str,
        *,
        system_prompt: str,
        stage: Literal["extract", "review", "admin_review"],
    ) -> LLMCallResult:
        api_key = self._resolve_api_key()
        model = self.active_model
        if model.startswith("models/"):
            model_path = model
        else:
            model_path = f"models/{model}"
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/{model_path}:generateContent"
            f"?key={api_key}"
        )
        body = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
            },
        }
        raw = self._post_json(url, body, headers={"Content-Type": "application/json"})
        candidates = raw.get("candidates") or []
        if not candidates:
            raise RuntimeError("Gemini không trả về candidates.")
        parts = candidates[0].get("content", {}).get("parts") or []
        text = "".join(part.get("text", "") for part in parts if isinstance(part, dict))
        if not text.strip():
            raise RuntimeError("Gemini response rỗng.")
        usage = _parse_gemini_usage(
            raw,
            provider=self.config.llm_provider.lower(),
            model=self.active_model,
            stage=stage,
        )
        return LLMCallResult(payload=_loads_json_object(text), usage=usage)

    def _post_json(
        self, url: str, body: dict[str, Any], *, headers: dict[str, str]
    ) -> dict[str, Any]:
        data = json.dumps(body).encode("utf-8")
        req = request.Request(url, data=data, headers=headers, method="POST")
        try:
            with request.urlopen(req, timeout=self.config.llm_timeout_seconds) as resp:
                payload = resp.read().decode("utf-8")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"LLM HTTP {exc.code}: {detail[:500]}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"LLM request failed: {exc}") from exc

        parsed = json.loads(payload)
        if not isinstance(parsed, dict):
            raise RuntimeError("LLM response is not a JSON object.")
        return parsed


def _parse_openai_usage(
    raw: dict[str, Any],
    *,
    provider: str,
    model: str,
    stage: Literal["extract", "review", "admin_review"],
) -> LLMTokenUsage:
    usage = raw.get("usage") or {}
    prompt_tokens = int(usage.get("prompt_tokens") or 0)
    completion_tokens = int(usage.get("completion_tokens") or 0)
    total_tokens = int(usage.get("total_tokens") or prompt_tokens + completion_tokens)
    return LLMTokenUsage(
        stage=stage,
        provider=provider,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
    )


def _parse_anthropic_usage(
    raw: dict[str, Any],
    *,
    provider: str,
    model: str,
    stage: Literal["extract", "review", "admin_review"],
) -> LLMTokenUsage:
    usage = raw.get("usage") or {}
    prompt_tokens = int(usage.get("input_tokens") or 0)
    completion_tokens = int(usage.get("output_tokens") or 0)
    return LLMTokenUsage(
        stage=stage,
        provider=provider,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
    )


def _parse_gemini_usage(
    raw: dict[str, Any],
    *,
    provider: str,
    model: str,
    stage: Literal["extract", "review", "admin_review"],
) -> LLMTokenUsage:
    meta = raw.get("usageMetadata") or {}
    prompt_tokens = int(meta.get("promptTokenCount") or 0)
    completion_tokens = int(meta.get("candidatesTokenCount") or 0)
    total_tokens = int(meta.get("totalTokenCount") or prompt_tokens + completion_tokens)
    return LLMTokenUsage(
        stage=stage,
        provider=provider,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
    )


def _read_env_key(env_name: str) -> str | None:
    value = os.getenv(env_name)
    if value and value.strip():
        return value.strip()
    return None


def _provider_configured_env(spec: LLMProviderSpec, config: PipelineConfig) -> str | None:
    for env_name in spec.api_key_env_vars:
        attr = _ENV_TO_CONFIG_ATTR.get(env_name)
        if attr:
            config_value = getattr(config, attr, None)
            if config_value and str(config_value).strip():
                return env_name
        if _read_env_key(env_name):
            return env_name
    return None


def list_supported_llm_providers() -> tuple[str, ...]:
    return tuple(sorted(LLM_PROVIDERS))


def _needs_llm_fallback(
    fields: ParsedFields | None,
    ocr_confidence: float,
    config: PipelineConfig,
) -> bool:
    if fields is None:
        return True
    if ocr_confidence < config.llm_fallback_min_ocr_confidence:
        return True
    if not fields.id_number or not fields.full_name:
        return True
    if not fields.place_of_origin or not fields.place_of_residence:
        return True
    if fields.nationality and "," in fields.nationality:
        return True
    if fields.sex is None:
        return True
    if _rule_value_is_low_quality("full_name", fields.full_name or ""):
        return True
    if _rule_value_is_low_quality(
        "place_of_residence", fields.place_of_residence or ""
    ):
        return True
    return False


def merge_rule_and_llm_fields(
    rule_fields: ParsedFields,
    llm_fields: ParsedFields,
    *,
    ocr_locked: frozenset[str] | None = None,
) -> ParsedFields:
    """Merge OCR/YOLO fields with LLM; locked layout fields are never overridden."""
    merged = rule_fields.model_dump()
    llm_data = llm_fields.model_dump()
    locked = ocr_locked or get_ocr_locked_fields(rule_fields)
    extra = dict(merged.get("extra") or {})
    if locked:
        extra["ocr_locked_fields"] = sorted(set(extra.get("ocr_locked_fields", [])) | set(locked))

    for field_name in _EXTRACTABLE_FIELDS:
        if field_name in locked:
            continue
        if field_name in _OCR_LOCKED_DATE_FIELDS:
            rule_value = merged.get(field_name)
            if rule_value and _valid_date(rule_value):
                continue
        llm_value = llm_data.get(field_name)
        if _llm_value_is_plausible(field_name, llm_value):
            merged[field_name] = llm_value

    merged["extra"] = extra
    return ParsedFields(**merged)


def _finalize_reviewed_fields(
    draft_fields: ParsedFields,
    reviewed_fields: ParsedFields,
    *,
    ocr_locked: frozenset[str] | None = None,
) -> ParsedFields:
    """Review pass wins when plausible; locked YOLO/OCR fields are never overridden."""
    merged = draft_fields.model_dump()
    reviewed_data = reviewed_fields.model_dump()
    locked = ocr_locked or get_ocr_locked_fields(draft_fields)
    extra = dict(merged.get("extra") or {})
    if locked:
        extra["ocr_locked_fields"] = sorted(set(extra.get("ocr_locked_fields", [])) | set(locked))

    for field_name in _EXTRACTABLE_FIELDS:
        if field_name in locked:
            continue
        if field_name in _OCR_LOCKED_DATE_FIELDS:
            draft_value = merged.get(field_name)
            if draft_value and _valid_date(draft_value):
                continue
        reviewed_value = reviewed_data.get(field_name)
        if _llm_value_is_plausible(field_name, reviewed_value):
            merged[field_name] = reviewed_value

    merged["extra"] = extra
    return ParsedFields(**merged)


_GARBAGE_ADDRESS_PHRASES = (
    "khong thai",
    "khong thài",
    "khong thời hạn",
    "khong thoi han",
    "co gia tri den",
    "có giá trị đến",
    "date of expiry",
    "for administrative",
    "director general",
    "social order",
    "personal identification",
    "index finger",
    "police department",
)


def _llm_value_is_plausible(field_name: str, value: object) -> bool:
    if value is None:
        return False
    if not isinstance(value, str):
        return False
    text = value.strip()
    if not text:
        return False

    if field_name == "id_number":
        return _valid_cccd_id(re.sub(r"\D", "", text))
    if field_name in {"date_of_birth", "issue_date", "expiry_date"}:
        return _valid_date(text)
    if field_name == "sex":
        return text in {"Nam", "Nữ"}
    if field_name == "full_name":
        return _looks_like_person_name(text)
    if field_name == "nationality":
        if "," in text and len(text) > 40:
            return False
        return len(text) >= 2
    if field_name in {"place_of_origin", "place_of_residence", "issue_place"}:
        lower = text.lower()
        if any(phrase in lower for phrase in _GARBAGE_ADDRESS_PHRASES):
            return False
        if re.search(r"khong\s+th", lower):
            return False
        return len(text) >= 3
    return True


def _rule_value_is_low_quality(field_name: str, value: str) -> bool:
    text = value.strip()
    if not text:
        return False
    lower = text.lower()
    if any(phrase in lower for phrase in _GARBAGE_ADDRESS_PHRASES):
        return True
    if field_name == "full_name":
        if re.search(r"[!@#$%^&*0-9?]", text):
            return True
        if not _looks_like_person_name(text):
            return True
    if field_name == "sex":
        return lower not in {"nam", "nữ", "nu"}
    if field_name in {"place_of_origin", "place_of_residence"}:
        if re.search(r"khong\s+th", lower):
            return True
    return False


def _parse_llm_payload(payload: dict[str, Any]) -> ParsedFields:
    cleaned = {key: _normalize_field_value(key, payload.get(key)) for key in _EXTRACTABLE_FIELDS}
    if cleaned.get("nationality") is None:
        cleaned["nationality"] = "Việt Nam"
    return ParsedFields(**cleaned)


def _normalize_field_value(field_name: str, value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"null", "none", "unknown", "n/a"}:
        return None
    if field_name == "id_number":
        digits = re.sub(r"\D", "", text)
        return digits if _valid_cccd_id(digits) else None
    if field_name in {"date_of_birth", "issue_date", "expiry_date"}:
        match = re.search(r"(\d{2}[/.-]\d{2}[/.-]\d{4})", text)
        return match.group(1).replace("-", "/").replace(".", "/") if match else None
    if field_name == "sex":
        lower = text.lower().strip()
        if lower in {"n", "nu", "nữ", "female", "f"}:
            return "Nữ"
        if lower.startswith("nam") or lower in {"m", "male"}:
            return "Nam"
        if lower.startswith("nữ") or "ữ" in text:
            return "Nữ"
    if field_name == "full_name" and not _looks_like_person_name(text):
        return None
    return text


def _loads_json_object(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise RuntimeError("LLM JSON payload must be an object.")
    return parsed


def _valid_cccd_id(value: object) -> bool:
    return isinstance(value, str) and bool(_CCCD_ID_PATTERN.fullmatch(value))


def _valid_date(value: object) -> bool:
    return isinstance(value, str) and bool(_DATE_PATTERN.fullmatch(value))
