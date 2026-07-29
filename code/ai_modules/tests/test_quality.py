import cv2
import numpy as np

from ekyc_document.quality_check import assess_image_quality


def _solid_image(value: int, size: int = 400) -> np.ndarray:
    gray = np.full((size, size), value, dtype=np.uint8)
    return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)


def test_dark_image_warns():
    result = assess_image_quality(_solid_image(30))
    assert result.score < 0.8
    assert any("tối" in w.lower() for w in result.warnings)


def test_sharp_checkerboard_scores_higher_than_blur():
    size = 400
    block = 20
    grid = np.indices((size, size)).sum(axis=0) // block % 2
    image = (grid * 255).astype(np.uint8)
    image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)

    sharp = assess_image_quality(image)
    blurred = assess_image_quality(cv2.GaussianBlur(image, (21, 21), 0))
    assert sharp.details.blur > blurred.details.blur


def test_clean_digital_capture_warns_as_possible_screenshot():
    image = np.full((420, 640, 3), 245, dtype=np.uint8)
    cv2.rectangle(image, (60, 60), (580, 330), (230, 230, 230), -1)
    cv2.rectangle(image, (60, 60), (580, 330), (20, 20, 20), 3)
    for index in range(8):
        y = 95 + index * 26
        cv2.rectangle(image, (190, y), (500, y + 10), (20, 20, 20), -1)
    cv2.rectangle(image, (90, 100), (160, 190), (20, 20, 20), -1)

    result = assess_image_quality(image)

    assert result.details.screenshot < 0.55
    assert any("chụp màn hình" in warning for warning in result.warnings)


def test_yolo_corners_skip_contour_corner_warning(monkeypatch):
    from dataclasses import replace
    from pathlib import Path

    from ekyc_document.config import PipelineConfig
    from ekyc_document.ocr_stack.layout_detect import LayoutField

    model_path = Path(__file__).resolve().parents[2] / "models" / "cccd_layout_yolov11.pt"
    if not model_path.is_file():
        import pytest

        pytest.skip("cccd_layout_yolov11.pt not available")

    image = _solid_image(120, size=400)

    def fake_detect(_self, _image):
        return [
            LayoutField(label="top_left", bbox=(10, 10, 30, 30), confidence=0.9),
            LayoutField(label="top_right", bbox=(350, 10, 370, 30), confidence=0.9),
            LayoutField(label="bottom_right", bbox=(350, 350, 370, 370), confidence=0.9),
            LayoutField(label="bottom_left", bbox=(10, 350, 30, 370), confidence=0.9),
        ]

    monkeypatch.setattr(
        "ekyc_document.ocr_stack.layout_detect.YOLOLayoutDetector.detect",
        fake_detect,
    )

    config = replace(
        PipelineConfig(),
        use_yolo_layout_pipeline=True,
        yolo_layout_model=model_path,
    )
    result = assess_image_quality(image, config)

    assert result.details.corners >= 0.85
    assert not any("Không phát hiện đủ 4 góc" in warning for warning in result.warnings)
