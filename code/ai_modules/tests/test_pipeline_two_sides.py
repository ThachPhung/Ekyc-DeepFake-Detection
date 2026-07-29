from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np

from ekyc_document.config import PipelineConfig
from ekyc_document.pipeline import DocumentPipeline, _merge_missing_back_side_fields
from ekyc_document.schemas import ParsedFields, QualityDetail


def _quality_result():
    return MagicMock(
        score=0.9,
        warnings=[],
        details=QualityDetail(
            blur=0.9,
            brightness=0.9,
            contrast=0.9,
            glare=0.9,
            corners=0.9,
        ),
    )


def _blank_image() -> np.ndarray:
    return np.zeros((200, 320, 3), dtype=np.uint8)


def test_merge_missing_back_side_fields_fills_issue_only():
    fields = ParsedFields(
        id_number="038202012897",
        full_name="Phùng Văn Thạch",
        date_of_birth="06/01/2002",
    )
    back_text = """
Đặc điểm nhận dạng / Personal identification:
Ngày cấp / Date of issue: 29/09/2022
Nơi cấp: Cục Cảnh sát quản lý hành chính về trật tự xã hội
"""

    merged = _merge_missing_back_side_fields(
        fields,
        back_text,
        document_type="CCCD",
    )

    assert merged is not None
    assert merged.id_number == "038202012897"
    assert merged.issue_date == "29/09/2022"
    assert merged.issue_place == "Cục Cảnh sát quản lý hành chính về trật tự xã hội"


def test_analyze_two_sides_parses_front_and_back_separately():
    config = PipelineConfig()
    pipeline = DocumentPipeline(config)

    llm_mock = MagicMock()
    llm_mock.should_run.return_value = False
    pipeline._llm = llm_mock

    front_ocr = MagicMock(
        lines=[],
        confidence=0.95,
        raw_text="FRONT OCR",
        engine="rapidocr_ppocrv6",
    )
    back_ocr = MagicMock(
        lines=[],
        confidence=0.93,
        raw_text="BACK OCR",
        engine="rapidocr_ppocrv6",
    )

    with (
        patch.object(
            pipeline,
            "_prepare_document_image",
            return_value=(_blank_image(), MagicMock(warning=None), _blank_image()),
        ),
        patch("ekyc_document.pipeline.assess_image_quality", return_value=_quality_result()),
        patch.object(pipeline.ocr, "run", side_effect=[front_ocr, back_ocr]),
        patch(
            "ekyc_document.pipeline.merge_two_sides",
            return_value=MagicMock(
                document_type="CCCD",
                fields=ParsedFields(id_number="031201000716", issue_date="29/09/2022"),
                warnings=[],
            ),
        ) as merge_mock,
    ):
        result = pipeline.analyze_two_sides(
            _blank_image(),
            _blank_image(),
            document_type_hint="CCCD",
            save_private_record=False,
            expect_document_face=False,
        )

    merge_mock.assert_called_once_with(
        "FRONT OCR",
        "BACK OCR",
        forced_type="CCCD",
    )
    assert result.parsed_fields is not None
    assert result.parsed_fields.id_number == "031201000716"
    assert result.parsed_fields.issue_date == "29/09/2022"
