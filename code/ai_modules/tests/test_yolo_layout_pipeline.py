"""Tests for YOLO layout pipeline helpers."""

from __future__ import annotations

from ekyc_document.yolo_layout_pipeline import (
    LayoutSideExtraction,
    build_two_sides_llm_text,
    layout_pipeline_ready,
    validate_cccd_two_sides_id,
)
from ekyc_document.config import PipelineConfig


def test_validate_cccd_two_sides_id_match():
    ok, warnings = validate_cccd_two_sides_id(
        "001234567890",
        "[MRZ]\nIDVNM001234567890<<8",
    )
    assert ok is True
    assert warnings == []


def test_validate_cccd_two_sides_id_match_embedded_in_mrz_line():
    ok, warnings = validate_cccd_two_sides_id(
        "031201000716",
        "IDVNM2010007163031201000716<<3\nLUONG<<QUOC<DOAN<<<<<<<<<<<<",
    )
    assert ok is True
    assert warnings == []


def test_validate_cccd_two_sides_id_mismatch():
    ok, warnings = validate_cccd_two_sides_id("001234567890", "no id here")
    assert ok is False
    assert warnings


def test_build_two_sides_llm_text():
    front = LayoutSideExtraction(
        side="front",
        layout_fields=[],
        labeled_text="[ID_NUMBER]\n001234567890",
    )
    back = LayoutSideExtraction(
        side="back",
        layout_fields=[],
        labeled_text="[MRZ]\n001234567890",
    )
    text = build_two_sides_llm_text(front, back)
    assert "[MAT_TRUOC]" in text
    assert "[MAT_SAU]" in text


def test_apply_two_sides_field_policy_clears_back_when_mismatch():
    from ekyc_document.schemas import ParsedFields
    from ekyc_document.yolo_layout_pipeline import apply_two_sides_field_policy

    merged = ParsedFields(
        id_number="079193003136",
        full_name="Nguyễn Ngọc Bảo Vi",
        issue_date="29/09/2022",
        issue_place="Cục Cảnh sát quản lý hành chính về trật tự xã hội",
        expiry_date="30/05/2026",
    )
    front_text = "[EXPIRY_DATE]\nCó giá trị đến: 06/10/2033"
    result = apply_two_sides_field_policy(
        merged,
        front_labeled_text=front_text,
        sides_ok=False,
        document_type="CCCD",
    )
    assert result is not None
    assert result.issue_date is None
    assert result.issue_place is None
    assert result.expiry_date == "06/10/2033"


def test_layout_pipeline_ready_when_model_missing(tmp_path, monkeypatch):
    config = PipelineConfig()
    monkeypatch.setattr(config, "yolo_layout_model", tmp_path / "missing.pt")
    assert layout_pipeline_ready(config) is False
