"""Tests for YOLO + DBNet + VietOCR OCR stack helpers."""

from __future__ import annotations

import cv2
import numpy as np

from ekyc_document.config import PipelineConfig
from ekyc_document.ocr_stack.document_warp import _find_contour_quad, _order_corners, warp_document
from ekyc_document.ocr_stack.layout_detect import YOLOLayoutDetector


def _synthetic_card_image() -> np.ndarray:
    image = np.full((480, 760, 3), 240, dtype=np.uint8)
    cv2.rectangle(image, (40, 40), (720, 440), (20, 20, 20), 4)
    cv2.putText(
        image,
        "CAN CUOC CONG DAN",
        (80, 120),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.0,
        (0, 0, 0),
        2,
        cv2.LINE_AA,
    )
    return image


def test_order_corners_sorts_quadrilateral() -> None:
    points = np.array(
        [
            [10, 10],
            [200, 12],
            [205, 120],
            [8, 118],
        ],
        dtype=np.float32,
    )
    ordered = _order_corners(points)
    assert ordered[0][0] <= ordered[1][0]
    assert ordered[0][1] <= ordered[3][1]


def test_contour_quad_detects_synthetic_card() -> None:
    image = _synthetic_card_image()
    quad = _find_contour_quad(image)
    assert quad is not None
    assert quad.shape == (4, 2)


def test_warp_document_uses_contour_fallback_when_layout_corners_missing() -> None:
    from dataclasses import replace

    config = replace(
        PipelineConfig(),
        yolo_layout_model=None,
        document_warp_enabled=True,
        document_warp_fallback="contour",
    )

    result = warp_document(_synthetic_card_image(), config)
    assert result.applied is True
    assert result.method == "contour"
    assert result.image.shape[0] > 0


def test_warp_document_uses_yolo_layout_corner_labels(monkeypatch) -> None:
    from dataclasses import replace
    from pathlib import Path

    from ekyc_document.ocr_stack.layout_detect import LayoutField

    model_path = Path(__file__).resolve().parents[2] / "models" / "cccd_layout_yolov11.pt"
    if not model_path.is_file():
        import pytest

        pytest.skip("cccd_layout_yolov11.pt not available")

    image = _synthetic_card_image()
    config = replace(
        PipelineConfig(),
        yolo_layout_model=model_path,
        use_yolo_layout_pipeline=True,
        document_warp_enabled=True,
        document_warp_fallback="none",
    )

    def fake_detect(_self, _image):
        return [
            LayoutField(label="top_left", bbox=(40, 40, 60, 60), confidence=0.9),
            LayoutField(label="top_right", bbox=(700, 40, 720, 60), confidence=0.9),
            LayoutField(label="bottom_right", bbox=(700, 420, 720, 440), confidence=0.9),
            LayoutField(label="bottom_left", bbox=(40, 420, 60, 440), confidence=0.9),
        ]

    monkeypatch.setattr(
        "ekyc_document.ocr_stack.layout_detect.YOLOLayoutDetector.detect",
        fake_detect,
    )
    result = warp_document(image, config)

    assert result.applied is True
    assert result.method == "yolo_layout_corners"
    assert result.corners is not None


def test_layout_detector_falls_back_to_full_page_without_model() -> None:
    from dataclasses import replace

    config = replace(PipelineConfig(), yolo_layout_model=None)
    detector = YOLOLayoutDetector(config)
    image = _synthetic_card_image()
    fields = detector.detect(image)
    assert len(fields) == 1
    assert fields[0].label == "full_page"
