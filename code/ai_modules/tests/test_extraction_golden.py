from __future__ import annotations

import json
from pathlib import Path

import pytest

from ekyc_document.field_polish import polish_extracted_fields
from ekyc_document.parser import merge_two_sides, parse_document

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


def test_merge_two_sides_doan_fixture_without_llm() -> None:
    fixture = _load_fixture("doan_cccd_ocr.json")
    merged = merge_two_sides(
        fixture["front_ocr"],
        fixture["back_ocr"],
        forced_type="CCCD",
    )
    fields = polish_extracted_fields(merged.fields)
    assert fields is not None

    expected = fixture["expected"]
    assert fields.id_number == expected["id_number"]
    assert expected["full_name_contains"] in (fields.full_name or "")
    assert fields.date_of_birth == expected["date_of_birth"]
    assert fields.sex == expected["sex"]
    assert fields.nationality == expected["nationality"]
    assert expected["place_of_origin_contains"] in (fields.place_of_origin or "")
    assert expected["place_of_residence_contains"] in (fields.place_of_residence or "")
    assert expected["place_of_residence_not_contains"] not in (
        fields.place_of_residence or ""
    ).upper()
    assert fields.issue_date == expected["issue_date"]
    assert expected["issue_place_contains"] in (fields.issue_place or "")
    assert fields.expiry_date == expected["expiry_date"]


def test_merge_two_sides_avoids_back_side_boilerplate_in_residence() -> None:
    fixture = _load_fixture("doan_cccd_ocr.json")
    merged = merge_two_sides(
        fixture["front_ocr"],
        fixture["back_ocr"],
        forced_type="CCCD",
    )
    assert merged.fields.place_of_residence is not None
    assert "ADMINISTRATIVE" not in (merged.fields.place_of_residence or "").upper()
    assert "Ngô Quyền" in (merged.fields.place_of_residence or "")


def test_parse_mrz_expiry_from_back_side() -> None:
    fixture = _load_fixture("doan_cccd_ocr.json")
    back = parse_document(fixture["back_ocr"], forced_type="CCCD", side="back")
    assert back.fields.expiry_date == "30/05/2026"


@pytest.mark.slow
def test_pipeline_two_sides_on_doan_images() -> None:
    data_dir = Path(__file__).resolve().parents[2] / "data" / "Doan"
    front = data_dir / "front.jpg"
    back = data_dir / "back.jpg"
    if not front.is_file() or not back.is_file():
        pytest.skip("Doan sample images not available")

    from ekyc_document.pipeline import DocumentPipeline

    pipeline = DocumentPipeline()
    result = pipeline.analyze_two_sides(
        front,
        back,
        document_type_hint="CCCD",
        save_private_record=False,
        expect_document_face=False,
        skip_ocr_if_low_quality=False,
    )
    assert result.parsed_fields is not None
    assert result.parsed_fields.id_number == "031201000716"
    assert result.parsed_fields.issue_date == "29/09/2022"
    assert "ADMINISTRATIVE" not in (
        result.parsed_fields.place_of_residence or ""
    ).upper()
    assert result.parsed_fields.expiry_date == "30/05/2026"
