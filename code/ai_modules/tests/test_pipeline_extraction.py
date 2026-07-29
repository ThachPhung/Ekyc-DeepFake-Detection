from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np

from ekyc_document.config import PipelineConfig
from ekyc_document.llm_extract import LLMExtractResult
from ekyc_document.pipeline import DocumentPipeline
from ekyc_document.schemas import FaceResult, ParsedFields, QualityDetail


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


def test_pipeline_uses_llm_for_text_not_rule_parser_when_ready():
    config = PipelineConfig()
    pipeline = DocumentPipeline(config)

    llm_fields = ParsedFields(
        id_number="001064010140",
        full_name="VŨ HÀ DƯƠNG",
        place_of_residence="Số 43 Hàng Bắc, Hoàn Kiếm, Hà Nội",
    )
    llm_mock = MagicMock()
    llm_mock.should_run.return_value = True
    llm_mock.extract.return_value = LLMExtractResult(
        fields=llm_fields,
        used=True,
        reviewed=True,
        provider="openai",
        model="gpt-4o-mini",
    )
    pipeline._llm = llm_mock

    face_mock = MagicMock()
    face_mock.extract.return_value = FaceResult(
        detected=True,
        confident=True,
        quality_score=0.9,
    )
    pipeline._face = face_mock

    with (
        patch.object(
            pipeline,
            "_prepare_document_image",
            return_value=(_blank_image(), MagicMock(warning=None), _blank_image()),
        ),
        patch(
            "ekyc_document.pipeline.assess_image_quality",
            return_value=_quality_result(),
        ),
        patch.object(
            pipeline.ocr,
            "run",
            return_value=MagicMock(
                lines=[],
                confidence=0.95,
                raw_text="OCR SAMPLE TEXT",
                engine="rapidocr_ppocrv6",
            ),
        ),
        patch(
            "ekyc_document.pipeline.parse_document",
            return_value=MagicMock(
                document_type="CCCD",
                fields=ParsedFields(id_number="001064010140"),
                warnings=[],
            ),
        ) as parse_mock,
    ):
        result = pipeline.analyze(
            _blank_image(),
            document_type_hint="CCCD",
            save_private_record=False,
            expect_document_face=True,
        )

    llm_mock.extract.assert_called_once()
    parse_mock.assert_called_once()
    assert result.parsed_fields is not None
    assert result.parsed_fields.full_name == "Vũ Hà Dương"
    assert any("LLM đã review tổng thể" in warning for warning in result.warnings)


def test_pipeline_falls_back_to_rule_parser_when_llm_unavailable():
    config = PipelineConfig()
    pipeline = DocumentPipeline(config)

    llm_mock = MagicMock()
    llm_mock.should_run.return_value = False
    pipeline._llm = llm_mock

    face_mock = MagicMock()
    face_mock.extract.return_value = FaceResult(detected=False)
    pipeline._face = face_mock

    with (
        patch.object(
            pipeline,
            "_prepare_document_image",
            return_value=(_blank_image(), MagicMock(warning=None), _blank_image()),
        ),
        patch(
            "ekyc_document.pipeline.assess_image_quality",
            return_value=_quality_result(),
        ),
        patch.object(
            pipeline.ocr,
            "run",
            return_value=MagicMock(
                lines=[],
                confidence=0.95,
                raw_text="001064010140 NGUYEN VAN A",
                engine="rapidocr_ppocrv6",
            ),
        ),
        patch(
            "ekyc_document.pipeline.parse_document",
            return_value=MagicMock(
                document_type="CCCD",
                fields=ParsedFields(id_number="001064010140", full_name="NGUYEN VAN A"),
                warnings=[],
            ),
        ) as parse_mock,
    ):
        result = pipeline.analyze(
            _blank_image(),
            document_type_hint="CCCD",
            save_private_record=False,
            expect_document_face=False,
        )

    llm_mock.extract.assert_not_called()
    parse_mock.assert_called_once()
    assert result.parsed_fields is not None
    assert result.parsed_fields.id_number == "001064010140"
