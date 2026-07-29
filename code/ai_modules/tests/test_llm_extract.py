from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from ekyc_document.config import PipelineConfig
from ekyc_document.llm_extract import (
    LLMCallResult,
    LLMFieldExtractor,
    LLM_PROVIDERS,
    _needs_llm_fallback,
    _parse_anthropic_usage,
    _parse_gemini_usage,
    _parse_openai_usage,
    list_supported_llm_providers,
    merge_rule_and_llm_fields,
)
from ekyc_document.llm_usage_metrics import llm_usage_metrics, record_llm_usage
from ekyc_document.schemas import DocumentType, LLMUsageSummary, ParsedFields


def test_supported_providers_include_openai_gemini_deepseek():
    providers = list_supported_llm_providers()
    assert "openai" in providers
    assert "gemini" in providers
    assert "deepseek" in providers
    assert "anthropic" in providers


def test_needs_llm_fallback_when_origin_missing():
    fields = ParsedFields(
        id_number="001060018452",
        full_name="NGUYEN HUY KHOI",
        place_of_residence="Ha Noi",
    )
    config = PipelineConfig()
    assert _needs_llm_fallback(fields, 0.95, config) is True


def test_merge_prefers_llm_when_nationality_contains_address():
    rule = ParsedFields(
        id_number="001060018452",
        nationality="Nationelity Việt Nam Hong Phong, Thanh Mien, Hai Duong",
        place_of_origin=None,
    )
    llm = ParsedFields(
        id_number="001060018452",
        nationality="Việt Nam",
        place_of_origin="Hồng Phong, Thanh Miện, Hải Dương",
    )
    merged = merge_rule_and_llm_fields(rule, llm)
    assert merged.nationality == "Việt Nam"
    assert merged.place_of_origin == "Hồng Phong, Thanh Miện, Hải Dương"


def test_merge_prefers_llm_when_rule_name_and_address_are_garbage():
    rule = ParsedFields(
        id_number="001140010337",
        full_name="NGUYĚN TH! TÍNH",
        place_of_residence="Hoàn Kiếm, Hà Nội, Khong thài han",
        sex="ON",
    )
    llm = ParsedFields(
        id_number="001140010337",
        full_name="NGUYỄN THỊ TÍNH",
        place_of_residence="31 Hàng Bạc, Hoàn Kiếm, Hà Nội",
        sex="Nữ",
    )
    merged = merge_rule_and_llm_fields(rule, llm)
    assert merged.full_name == "NGUYỄN THỊ TÍNH"
    assert merged.place_of_residence == "31 Hàng Bạc, Hoàn Kiếm, Hà Nội"
    assert merged.sex == "Nữ"


def test_merge_prefers_llm_when_rule_name_is_field_label():
    rule = ParsedFields(
        id_number="001163006372",
        full_name="Ngày Sinh Date Of Bith",
    )
    llm = ParsedFields(
        id_number="001163006372",
        full_name="NGUYỄN THỊ NGA",
    )
    merged = merge_rule_and_llm_fields(rule, llm)
    assert merged.full_name == "NGUYỄN THỊ NGA"


def test_merge_llm_wins_when_both_rule_and_llm_are_valid():
    rule = ParsedFields(
        id_number="001064010140",
        full_name="VŨ HÀ DƯƠNG",
        place_of_residence="Số 43 Hàng Bắc, Hoàn Kiếm, Hà Nội",
        sex="Nam",
    )
    llm = ParsedFields(
        id_number="001064010140",
        full_name="Vũ Hà Dương",
        place_of_residence="Số 43 Hàng Bắc, Hoàn Kiếm, Hà Nội",
        sex="Nam",
        expiry_date="27/07/2044",
    )
    merged = merge_rule_and_llm_fields(rule, llm)
    assert merged.full_name == "Vũ Hà Dương"
    assert merged.expiry_date == "27/07/2044"


def test_merge_keeps_rule_when_llm_field_invalid():
    rule = ParsedFields(
        id_number="001064010140",
        full_name="VŨ HÀ DƯƠNG",
        place_of_residence="Số 43 Hàng Bắc, Hoàn Kiếm, Hà Nội",
    )
    llm = ParsedFields(
        id_number="001064010140",
        full_name="Ngày Sinh Date Of Bith",
        place_of_residence="Số 43 Hàng Bắc, Hoàn Kiếm, Hà Nội",
    )
    merged = merge_rule_and_llm_fields(rule, llm)
    assert merged.full_name == "VŨ HÀ DƯƠNG"


@pytest.mark.parametrize(
    ("provider", "api_key_attr", "api_key_value"),
    [
        ("openai", "openai_api_key", "openai-test"),
        ("deepseek", "deepseek_api_key", "deepseek-test"),
        ("gemini", "gemini_api_key", "gemini-test"),
        ("anthropic", "anthropic_api_key", "anthropic-test"),
    ],
)
def test_provider_uses_own_api_key(provider, api_key_attr, api_key_value, monkeypatch):
    for env_name in (
        "OPENAI_API_KEY",
        "DEEPSEEK_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "ANTHROPIC_API_KEY",
        "EKYC_LLM_API_KEY",
    ):
        monkeypatch.delenv(env_name, raising=False)

    config = PipelineConfig()
    config.llm_extract_enabled = True
    config.llm_provider = provider
    config.llm_api_key = None
    config.openai_api_key = None
    config.deepseek_api_key = None
    config.gemini_api_key = None
    config.google_api_key = None
    config.anthropic_api_key = None
    setattr(config, api_key_attr, api_key_value)

    extractor = LLMFieldExtractor(config)
    assert extractor.is_ready() is True
    assert extractor._resolve_api_key() == api_key_value
    assert extractor.active_model == LLM_PROVIDERS[provider].default_model


def test_llm_extract_runs_review_pass_after_merge(monkeypatch):
    config = PipelineConfig()
    config.llm_extract_enabled = True
    config.llm_review_enabled = True
    config.llm_provider = "openai"
    config.openai_api_key = "test-key"
    config.llm_model = "gpt-4o-mini"

    extractor = LLMFieldExtractor(config)
    rule = ParsedFields(id_number="001064010140", full_name="NGUYEN VAN A")
    calls: list[str] = []

    def fake_call_llm(
        raw_ocr_text: str,
        *,
        document_type: DocumentType,
        system_prompt: str,
        user_prompt: str | None = None,
        stage: str = "extract",
    ) -> LLMCallResult:
        calls.append(system_prompt[:20])
        if len(calls) == 1:
            payload = {
                "id_number": "001064010140",
                "full_name": "NGUYEN VAN A",
                "place_of_residence": "So 43 Hang Bac, Hoan Kiem, Ha Noi",
            }
        else:
            payload = {
                "id_number": "001064010140",
                "full_name": "Vũ Hà Dương",
                "place_of_residence": "Số 43 Hàng Bắc, Hoàn Kiếm, Hà Nội",
                "sex": "Nam",
            }
        return LLMCallResult(
            payload=payload,
            usage=_parse_openai_usage(
                {
                    "usage": {
                        "prompt_tokens": 100 + len(calls),
                        "completion_tokens": 40 + len(calls),
                        "total_tokens": 140 + len(calls) * 2,
                    }
                },
                provider="openai",
                model="gpt-4o-mini",
                stage=stage,  # type: ignore[arg-type]
            ),
        )

    monkeypatch.setattr(extractor, "_call_llm", fake_call_llm)
    result = extractor.extract(
        "OCR text sample",
        document_type="CCCD",
        rule_fields=rule,
        ocr_confidence=0.9,
    )

    assert result.used is True
    assert result.reviewed is True
    assert len(calls) == 2
    assert result.fields is not None
    assert result.fields.full_name == "Vũ Hà Dương"
    assert result.fields.place_of_residence == "Số 43 Hàng Bắc, Hoàn Kiếm, Hà Nội"
    assert result.usage is not None
    assert result.usage.call_count == 2
    assert result.usage.total_tokens == 286


def test_llm_extract_openai_mock():
    config = PipelineConfig()
    config.llm_extract_enabled = True
    config.llm_extract_mode = "always"
    config.llm_provider = "openai"
    config.openai_api_key = "test-key"
    config.llm_model = "gpt-4o-mini"

    extractor = LLMFieldExtractor(config)
    rule = ParsedFields(id_number="001064010140", sex=None, place_of_origin=None)

    mock_response = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "id_number": "001064010140",
                            "full_name": "VŨ HÀ DƯƠNG",
                            "date_of_birth": "27/07/1964",
                            "sex": "Nam",
                            "nationality": "Việt Nam",
                            "place_of_origin": "Hồng Phong, Thanh Miện, Hải Dương",
                            "place_of_residence": "Số 43 Hàng Bắc, Hoàn Kiếm, Hà Nội",
                            "issue_date": "29/09/2022",
                            "issue_place": "Cục Cảnh sát quản lý hành chính về trật tự xã hội",
                            "expiry_date": "27/07/2024",
                        },
                        ensure_ascii=False,
                    )
                }
            }
        ],
        "usage": {
            "prompt_tokens": 180,
            "completion_tokens": 95,
            "total_tokens": 275,
        },
    }

    with patch.object(extractor, "_post_json", return_value=mock_response):
        result = extractor.extract(
            "OCR text sample",
            document_type="CCCD",
            rule_fields=rule,
            ocr_confidence=0.9,
        )

    assert result.used is True
    assert result.fields is not None
    assert result.fields.sex == "Nam"
    assert result.fields.place_of_origin is not None
    assert result.usage is not None
    assert result.usage.extract is not None
    assert result.usage.extract.total_tokens == 275


def test_parse_provider_usage_shapes() -> None:
    openai_usage = _parse_openai_usage(
        {"usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}},
        provider="openai",
        model="gpt-4o-mini",
        stage="extract",
    )
    anthropic_usage = _parse_anthropic_usage(
        {"usage": {"input_tokens": 20, "output_tokens": 8}},
        provider="anthropic",
        model="claude-sonnet-4-20250514",
        stage="review",
    )
    gemini_usage = _parse_gemini_usage(
        {
            "usageMetadata": {
                "promptTokenCount": 30,
                "candidatesTokenCount": 12,
                "totalTokenCount": 42,
            }
        },
        provider="gemini",
        model="gemini-2.0-flash",
        stage="extract",
    )

    summary = LLMUsageSummary.from_calls(openai_usage, anthropic_usage)
    assert summary.call_count == 2
    assert summary.total_tokens == 43
    assert gemini_usage.total_tokens == 42


def test_llm_usage_metrics_accumulates() -> None:
    usage = LLMUsageSummary.from_calls(
        _parse_openai_usage(
            {"usage": {"prompt_tokens": 11, "completion_tokens": 4, "total_tokens": 15}},
            provider="openai",
            model="gpt-4o-mini",
            stage="extract",
        ),
        _parse_openai_usage(
            {"usage": {"prompt_tokens": 9, "completion_tokens": 6, "total_tokens": 15}},
            provider="openai",
            model="gpt-4o-mini",
            stage="review",
        ),
    )
    before = llm_usage_metrics()
    record_llm_usage(usage)
    after = llm_usage_metrics()

    assert after["document_requests_with_llm"] == int(before["document_requests_with_llm"]) + 1
    assert after["total_tokens"] == int(before["total_tokens"]) + 30
    assert after["extract_tokens"] == int(before["extract_tokens"]) + 15
    assert after["review_tokens"] == int(before["review_tokens"]) + 15


def test_llm_extract_deepseek_uses_deepseek_endpoint():
    config = PipelineConfig()
    config.llm_extract_enabled = True
    config.llm_extract_mode = "always"
    config.llm_provider = "deepseek"
    config.deepseek_api_key = "ds-test"
    config.llm_model = "deepseek-chat"

    extractor = LLMFieldExtractor(config)
    mock_response = {
        "choices": [{"message": {"content": json.dumps({"id_number": "001064010140"})}}]
    }

    with patch.object(extractor, "_post_json", return_value=mock_response) as post:
        extractor.extract("ocr", rule_fields=ParsedFields(), ocr_confidence=0.9)

    assert post.call_args.args[0] == "https://api.deepseek.com/v1/chat/completions"


def test_llm_extract_gemini_uses_gemini_endpoint(monkeypatch):
    for env_name in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "EKYC_LLM_API_KEY"):
        monkeypatch.delenv(env_name, raising=False)

    config = PipelineConfig()
    config.llm_extract_enabled = True
    config.llm_extract_mode = "always"
    config.llm_provider = "gemini"
    config.gemini_api_key = "gem-test"
    config.llm_model = "gemini-2.0-flash"

    extractor = LLMFieldExtractor(config)
    mock_response = {
        "candidates": [{"content": {"parts": [{"text": json.dumps({"id_number": "001064010140"})}]}}]
    }

    with patch.object(extractor, "_post_json", return_value=mock_response) as post:
        extractor.extract("ocr", rule_fields=ParsedFields(), ocr_confidence=0.9)

    url = post.call_args.args[0]
    assert "generativelanguage.googleapis.com" in url
    assert "models/gemini-2.0-flash:generateContent" in url
    assert "key=gem-test" in url


def test_llm_extract_skips_without_api_key(monkeypatch):
    for env_name in (
        "OPENAI_API_KEY",
        "DEEPSEEK_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "ANTHROPIC_API_KEY",
        "EKYC_LLM_API_KEY",
    ):
        monkeypatch.delenv(env_name, raising=False)

    config = PipelineConfig()
    config.llm_extract_enabled = True
    config.llm_provider = "openai"
    config.llm_api_key = None
    config.openai_api_key = None

    extractor = LLMFieldExtractor(config)
    result = extractor.extract("ocr", rule_fields=ParsedFields(), ocr_confidence=0.5)
    assert result.used is False


def test_is_ready_false_without_api_key(monkeypatch):
    for env_name in (
        "OPENAI_API_KEY",
        "DEEPSEEK_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "ANTHROPIC_API_KEY",
        "EKYC_LLM_API_KEY",
    ):
        monkeypatch.delenv(env_name, raising=False)

    config = PipelineConfig()
    config.llm_extract_enabled = True
    config.openai_api_key = None
    extractor = LLMFieldExtractor(config)
    assert extractor.is_ready() is False
    diagnostics = extractor.diagnostics()
    assert diagnostics["ready"] is False


def test_diagnostics_lists_all_providers(monkeypatch):
    for env_name in (
        "OPENAI_API_KEY",
        "DEEPSEEK_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "ANTHROPIC_API_KEY",
    ):
        monkeypatch.delenv(env_name, raising=False)

    config = PipelineConfig()
    config.llm_provider = "gemini"
    config.gemini_api_key = "gem-test"
    diagnostics = LLMFieldExtractor(config).diagnostics()
    assert "providers" in diagnostics
    assert diagnostics["providers"]["gemini"]["configured"] is True
    assert diagnostics["providers"]["openai"]["configured"] is False
