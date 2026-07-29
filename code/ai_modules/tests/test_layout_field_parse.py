"""Tests for YOLO layout block parsing and OCR-locked date fields."""

from __future__ import annotations

from datetime import datetime

from ekyc_document.layout_field_parse import (
    apply_document_status_checks,
    evaluate_document_expiry,
    extract_layout_date,
    merge_layout_extractions,
    parse_labeled_layout_fields,
    validate_date_triplet,
)
from ekyc_document.llm_extract import merge_rule_and_llm_fields
from ekyc_document.parser import merge_two_sides
from ekyc_document.schemas import ParsedFields


def test_parse_date_of_birth_from_yolo_block():
    text = "[DATE_OF_BIRTH]\nNgày sinh / Date of birth: 30/05/2001\n"
    fields, locked = parse_labeled_layout_fields(text)
    assert fields.date_of_birth == "30/05/2001"
    assert "date_of_birth" in locked


def test_parse_all_dates_from_yolo_blocks():
    front = """
[DATE_OF_BIRTH]
30/05/2001

[EXPIRY_DATE]
Có giá trị đến: 06/10/2033
"""
    back = """
[ISSUE_DATE]
Ngày cấp / Date of issue: 29/09/2022
"""
    merged, locked = merge_layout_extractions(ParsedFields(), front, back)
    assert merged.date_of_birth == "30/05/2001"
    assert merged.issue_date == "29/09/2022"
    assert merged.expiry_date == "06/10/2033"
    assert "date_of_birth" in locked
    assert "issue_date" in locked
    assert "expiry_date" in locked


def test_ocr_digit_fix_in_layout_date():
    assert extract_layout_date("Ngày sinh: 3O/O5/2OO1") == "30/05/2001"


def test_merge_two_sides_uses_yolo_blocks_not_first_date():
    front = """
[DATE_OF_BIRTH]
12/05/1960

[EXPIRY_DATE]
06/10/2033
"""
    back = """
[ISSUE_DATE]
29/09/2022
"""
    result = merge_two_sides(front, back, forced_type="CCCD")
    assert result.fields.date_of_birth == "12/05/1960"
    assert result.fields.issue_date == "29/09/2022"
    assert result.fields.expiry_date == "06/10/2033"


def test_llm_cannot_override_locked_ocr_dates():
    rule = ParsedFields(
        id_number="001064010140",
        date_of_birth="30/05/2001",
        issue_date="29/09/2022",
        expiry_date="06/10/2033",
        extra={"ocr_locked_fields": ["date_of_birth", "issue_date", "expiry_date"]},
    )
    llm = ParsedFields(
        id_number="001064010140",
        date_of_birth="29/09/2022",
        issue_date="30/05/2001",
        expiry_date="29/09/2022",
    )
    merged = merge_rule_and_llm_fields(rule, llm)
    assert merged.date_of_birth == "30/05/2001"
    assert merged.issue_date == "29/09/2022"
    assert merged.expiry_date == "06/10/2033"


def test_llm_cannot_override_any_populated_date_even_without_lock_metadata():
    rule = ParsedFields(
        date_of_birth="30/05/2001",
        issue_date="29/09/2022",
        expiry_date="06/10/2033",
    )
    llm = ParsedFields(
        date_of_birth="29/09/2022",
        issue_date="06/10/2033",
        expiry_date="30/05/2001",
    )
    merged = merge_rule_and_llm_fields(rule, llm)
    assert merged.date_of_birth == "30/05/2001"
    assert merged.issue_date == "29/09/2022"
    assert merged.expiry_date == "06/10/2033"


def test_validate_date_triplet_detects_swapped_dates():
    fields = ParsedFields(
        date_of_birth="29/09/2022",
        issue_date="30/05/2001",
        expiry_date="06/10/2033",
    )
    warnings = validate_date_triplet(fields)
    assert any("Ngày sinh" in warning for warning in warnings)


def test_mrz_block_expiry_from_layout():
    back = "[MRZ]\nIDVNM001234567890<<8\nLUONG<<QUOC<DOAN<<<<<<<<<<<<\n6407279M2212299VNM<<<<<<<<<<<4"
    fields, locked = parse_labeled_layout_fields(back)
    assert fields.expiry_date is not None
    assert "expiry_date" in locked


def test_layout_first_ignores_wrong_rule_parser_values():
    front = """
[ID_NUMBER]
031201000716

[FULL_NAME]
LƯƠNG QUỐC DOÀN

[DATE_OF_BIRTH]
30/05/2001
"""
    rule = ParsedFields(
        id_number="001234567890",
        full_name="NGÀY SINH DATE OF BIRTH",
        date_of_birth="29/09/2022",
    )
    merged, locked = merge_layout_extractions(rule, front, "")
    assert merged.id_number == "031201000716"
    assert merged.full_name == "LƯƠNG QUỐC DOÀN"
    assert merged.date_of_birth == "30/05/2001"
    assert "id_number" in locked
    assert "full_name" in locked


def test_layout_blocks_strip_printed_labels_and_drop_bad_id_lock():
    front = """
[ID_NUMBER]
Số / No.: 003820201289

[FULL_NAME]
Ho và tên / Full name: Phùng Văn Thạch

[DATE_OF_BIRTH]
Ngày sinh / Date of birth: 06/01/2002

[SEX]
Giới tính / Sex: Nam

[NATIONALITY]
Quc tich Nationality: Việt Nam

[PLACE_OF_ORIGIN]
Quê quán / Place of origin: Hoång Hóa, Thanh Hóa

[PLACE_OF_RESIDENCE]
Nơi thường trú / Place of residence: Hồng Hóa, Thanh Hóa
"""
    fields, locked = parse_labeled_layout_fields(front)
    assert fields.id_number is None
    assert "id_number" not in locked
    assert fields.full_name == "Phùng Văn Thạch"
    assert fields.nationality == "Việt Nam"
    assert fields.place_of_origin == "Hoằng Hóa, Thanh Hóa"
    assert fields.place_of_residence == "Hoằng Hóa, Thanh Hóa"


def test_llm_cannot_override_locked_layout_name():
    rule = ParsedFields(
        id_number="031201000716",
        full_name="LƯƠNG QUỐC DOÀN",
        extra={"ocr_locked_fields": ["id_number", "full_name"]},
    )
    llm = ParsedFields(
        id_number="001234567890",
        full_name="NGUYỄN VĂN A",
    )
    merged = merge_rule_and_llm_fields(rule, llm)
    assert merged.id_number == "031201000716"
    assert merged.full_name == "LƯƠNG QUỐC DOÀN"


def test_evaluate_document_expired_in_past():
    is_expired, warning, meta = evaluate_document_expiry(
        "01/01/2020",
        now=datetime(2026, 7, 8),
    )
    assert is_expired is True
    assert warning is not None
    assert "hết hạn" in warning.lower()
    assert meta["document_expired"] is True
    assert meta["days_until_expiry"] < 0


def test_evaluate_document_still_valid():
    is_expired, warning, meta = evaluate_document_expiry(
        "01/01/2030",
        now=datetime(2026, 7, 8),
    )
    assert is_expired is False
    assert warning is None
    assert meta["document_expired"] is False
    assert meta["days_until_expiry"] > 0


def test_apply_document_status_checks_adds_warning():
    fields = ParsedFields(expiry_date="01/01/2020")
    warnings: list[str] = []
    updated = apply_document_status_checks(fields, warnings)
    assert updated is not None
    assert updated.extra.get("document_expired") is True
    assert any("hết hạn" in item.lower() for item in warnings)


def test_merge_two_sides_reports_expired_document():
    front = """
[DATE_OF_BIRTH]
30/05/2001
[EXPIRY_DATE]
01/01/2020
"""
    back = "[ISSUE_DATE]\n29/09/2015"
    result = merge_two_sides(front, back, forced_type="CCCD")
    assert result.fields.expiry_date == "01/01/2020"
    assert result.fields.extra.get("document_expired") is True
    assert any("hết hạn" in warning.lower() for warning in result.warnings)
