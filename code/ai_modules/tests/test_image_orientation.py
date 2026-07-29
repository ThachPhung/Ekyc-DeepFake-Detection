from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from ekyc_document.image_orientation import (
    auto_orient_document,
    is_landscape,
    is_portrait,
    rotate_bgr,
)
from ekyc_document.pipeline import DocumentPipeline


def test_is_portrait_and_landscape():
    portrait = np.zeros((800, 500, 3), dtype=np.uint8)
    landscape = np.zeros((500, 800, 3), dtype=np.uint8)
    assert is_portrait(portrait)
    assert not is_portrait(landscape)
    assert is_landscape(landscape)
    assert not is_landscape(portrait)


def test_rotate_bgr_roundtrip():
    landscape = np.zeros((400, 800, 3), dtype=np.uint8)
    portrait = rotate_bgr(landscape, 90)
    assert is_portrait(portrait)
    restored = rotate_bgr(portrait, 270)
    assert is_landscape(restored)


def test_auto_orient_portrait_cccd_image4():
    pytest.importorskip("rapidocr")
    image_path = Path(__file__).resolve().parents[2] / "data" / "Test" / "image4.png"
    if not image_path.is_file():
        pytest.skip("sample image4.png not available")

    landscape = cv2.imread(str(image_path))
    portrait = rotate_bgr(landscape, 90)

    pipeline = DocumentPipeline()
    oriented = auto_orient_document(portrait, pipeline.ocr)
    assert oriented.auto_rotated is True
    assert is_landscape(oriented.image)

    result = pipeline.analyze(
        portrait,
        document_type_hint="CCCD",
        save_private_record=False,
        expect_document_face=False,
    )
    assert result.parsed_fields is not None
    assert result.parsed_fields.id_number == "001163006372"
    assert result.parsed_fields.full_name is not None
    assert "NGA" in result.parsed_fields.full_name.upper()
    assert any("xoay" in warning.lower() for warning in result.warnings)
