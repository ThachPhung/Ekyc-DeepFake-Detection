from __future__ import annotations

import numpy as np
import pytest

from ekyc_document.onnx_models import (
    OnnxModelRegistry,
    _crop_face_minifasnet,
    _crop_face_with_scale,
    _minifasnet_live_score,
    _to_nchw_float_bgr255,
    _vit_pixel_values,
)
from ekyc_document.parser import _fix_ocr_common_errors, parse_document


def test_minifasnet_live_score_uses_class_one() -> None:
    probs = np.array([0.03, 0.94, 0.03], dtype=np.float32)
    assert _minifasnet_live_score(probs) == pytest.approx(0.94)


def test_to_nchw_float_bgr255_keeps_pixel_range() -> None:
    crop = np.full((80, 80, 3), 128, dtype=np.uint8)
    tensor = _to_nchw_float_bgr255(crop)
    assert tensor.shape == (1, 3, 80, 80)
    assert float(tensor.max()) == 128.0


def test_crop_face_minifasnet_returns_expected_size() -> None:
    image = np.zeros((200, 200, 3), dtype=np.uint8)
    crop = _crop_face_minifasnet(image, [60, 50, 80, 90], scale=2.7, out_size=(80, 80))
    assert crop.shape == (80, 80, 3)


def test_crop_face_with_scale_returns_expected_size() -> None:
    image = np.zeros((200, 200, 3), dtype=np.uint8)
    crop = _crop_face_with_scale(image, [60, 50, 80, 90], scale=2.7, out_size=(80, 80))
    assert crop.shape == (80, 80, 3)


def test_vit_pixel_values_are_local_imagenet_preprocess() -> None:
    crop = np.full((96, 96, 3), 128, dtype=np.uint8)
    tensor = _vit_pixel_values(crop, (224, 224))

    assert tensor.shape == (1, 3, 224, 224)
    assert tensor.dtype == np.float32
    assert np.isfinite(tensor).all()


def test_fix_ocr_common_errors_normalizes_labels() -> None:
    fixed = _fix_ocr_common_errors("HO VA TEN\nNGAY SINH\nCAN CUOC")
    assert "HỌ VÀ TÊN" in fixed
    assert "NGÀY SINH" in fixed
    assert "CĂN CƯỚC" in fixed


def test_parse_document_applies_ocr_fixes() -> None:
    raw = "\n".join(
        [
            "CĂN CUOC CONG DAN",
            "SO: 001234567890",
            "HO VA TEN",
            "NGUYEN VAN A",
            "NGAY SINH",
            "01/01/1990",
        ]
    )
    result = parse_document(raw, forced_type="CCCD")
    assert result.document_type == "CCCD"
    assert result.fields.full_name == "Nguyễn VAN A"


def test_onnx_registry_reports_missing_models(tmp_path) -> None:
    from ekyc_document.config import PipelineConfig

    config = PipelineConfig(
        models_dir=tmp_path,
        minifasnet_onnx_path=tmp_path / "minifasnet.onnx",
        minifasnet_int8_onnx_path=tmp_path / "minifasnet_v2se_int8.onnx",
        deepfake_onnx_path=tmp_path / "deepfake_detector.onnx",
        require_onnx_models=True,
    )
    registry = OnnxModelRegistry(config)
    missing = registry.ensure_required_models()
    assert "minifasnet.onnx" in missing
    assert "deepfake_detector.onnx" in missing


def test_onnx_smoke_test_reports_missing_without_crashing(tmp_path) -> None:
    from ekyc_document.config import PipelineConfig

    config = PipelineConfig(
        models_dir=tmp_path,
        minifasnet_onnx_path=tmp_path / "minifasnet.onnx",
        minifasnet_int8_onnx_path=tmp_path / "minifasnet_v2se_int8.onnx",
        deepfake_onnx_path=tmp_path / "deepfake_detector.onnx",
    )
    smoke = OnnxModelRegistry(config).smoke_test()

    assert smoke["ready"] is True
    assert smoke["checks"]["minifasnet"]["status"] == "missing"
    assert smoke["checks"]["deepfake"]["status"] == "missing"
