"""Central ONNX model loading and inference for eKYC AI."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from ekyc_document.config import PipelineConfig
from ekyc_document.liveness.crop import crop_face_minifasnet, minifasnet_live_score, to_minifasnet_tensor

IMAGENET_MEAN = np.asarray([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.asarray([0.229, 0.224, 0.225], dtype=np.float32)


@dataclass
class OnnxModelStatus:
    name: str
    path: str | None
    available: bool
    input_shape: list[Any] | None = None
    output_shape: list[Any] | None = None
    detail: str | None = None


class OnnxModelRegistry:
    """Lazy ONNXRuntime sessions for liveness and deepfake models."""

    def __init__(self, config: PipelineConfig | None = None) -> None:
        self.config = config or PipelineConfig()
        self._sessions: dict[str, Any] = {}

    def diagnostics(self) -> dict[str, object]:
        active_path = self._resolve_minifasnet_path()
        minifasnet = self._status(active_path, "minifasnet")
        deepfake = self._status(self.config.deepfake_onnx_path, "deepfake")
        return {
            "prefer_onnx": self.config.prefer_onnx,
            "require_onnx_models": self.config.require_onnx_models,
            "allow_heuristic_fallback": self.config.allow_heuristic_fallback,
            "minifasnet": minifasnet.__dict__,
            "minifasnet_fp32_path": str(self.config.minifasnet_onnx_path)
            if self.config.minifasnet_onnx_path
            else None,
            "minifasnet_int8_path": str(self.config.minifasnet_int8_onnx_path)
            if self.config.minifasnet_int8_onnx_path
            else None,
            "deepfake": deepfake.__dict__,
            "deepfake_preprocess": self.config.deepfake_preprocess,
            "minifasnet_crop_scale": self.config.minifasnet_crop_scale,
        }

    def ensure_required_models(self) -> list[str]:
        missing: list[str] = []
        if self.config.require_onnx_models:
            if not self._is_available(self._resolve_minifasnet_path()):
                missing.append("minifasnet.onnx")
            if not self._is_available(self.config.deepfake_onnx_path):
                missing.append("deepfake_detector.onnx")
        return missing

    def smoke_test(self) -> dict[str, object]:
        """Run tiny synthetic inference to verify model files and preprocess wiring."""
        synthetic = _synthetic_face_image()
        checks = {
            "minifasnet": self._smoke_minifasnet(synthetic),
            "deepfake": self._smoke_deepfake(synthetic),
        }
        return {
            "ready": all(item["status"] != "error" for item in checks.values()),
            "checks": checks,
        }

    def run_minifasnet(
        self,
        image_bgr: np.ndarray,
        bbox: list[int],
    ) -> tuple[float, str] | None:
        model_path = self._resolve_minifasnet_path()
        if not self._is_available(model_path):
            return None

        session_key = "minifasnet_int8" if self._is_int8_path(model_path) else "minifasnet"
        session = self._get_session(session_key, model_path)
        input_meta = session.get_inputs()[0]
        input_name = input_meta.name
        input_h, input_w = _spatial_dims(input_meta.shape)

        crop = crop_face_minifasnet(
            image_bgr,
            bbox,
            scale=self.config.minifasnet_crop_scale,
            out_size=(input_w, input_h),
        )
        tensor = to_minifasnet_tensor(crop)
        outputs = session.run(None, {input_name: tensor})
        logits = np.asarray(outputs[0]).reshape(-1)
        method = "minifasnet_v2_se_int8" if session_key == "minifasnet_int8" else "minifasnet_v2_onnx"
        if logits.size == 1:
            return _clip01(float(logits[0])), method
        probs = _softmax(logits)
        live_score = minifasnet_live_score(probs)
        return round(_clip01(live_score), 4), method

    def run_deepfake(self, face_crop_bgr: np.ndarray) -> tuple[float, str] | None:
        model_path = self.config.deepfake_onnx_path
        if not self._is_available(model_path):
            return None

        session = self._get_session("deepfake", model_path)
        input_meta = session.get_inputs()[0]
        input_name = input_meta.name
        input_h, input_w = _spatial_dims(input_meta.shape, default=224)

        tensor = self._deepfake_input_tensor(face_crop_bgr, input_name, (input_h, input_w))
        outputs = session.run(None, {input_name: tensor})
        logits = np.asarray(outputs[0]).reshape(-1)
        if logits.size == 1:
            fake_score = _clip01(1.0 / (1.0 + math.exp(-float(logits[0]))))
        else:
            probs = _softmax(logits)
            fake_index = _fake_class_index(probs.size)
            fake_score = float(probs[fake_index])
        method = "deepfake_vit_onnx"
        if input_name == "pixel_values":
            method = "deepfake_vit_onnx_hf_preprocess"
        return round(_clip01(fake_score), 4), method

    def _deepfake_input_tensor(
        self,
        face_crop_bgr: np.ndarray,
        input_name: str,
        size: tuple[int, int],
    ) -> np.ndarray:
        if input_name == "pixel_values" or self.config.deepfake_preprocess == "hf_vit":
            return _vit_pixel_values(face_crop_bgr, size)

        resized = cv2.resize(face_crop_bgr, size)
        if self.config.deepfake_preprocess == "simple":
            return _to_nchw_float01(resized)
        return _to_nchw_imagenet(resized)

    def _get_session(self, key: str, model_path: Path) -> Any:
        if key in self._sessions:
            return self._sessions[key]
        import onnxruntime as ort

        providers = (
            ["CUDAExecutionProvider", "CPUExecutionProvider"]
            if self.config.use_gpu
            else ["CPUExecutionProvider"]
        )
        session = ort.InferenceSession(str(model_path), providers=providers)
        self._sessions[key] = session
        return session

    def _smoke_minifasnet(self, image_bgr: np.ndarray) -> dict[str, object]:
        model_path = self._resolve_minifasnet_path()
        if not self._is_available(model_path):
            return {"status": "missing", "required": self.config.require_onnx_models}
        try:
            result = self.run_minifasnet(image_bgr, [36, 32, 88, 96])
            if result is None:
                return {"status": "missing", "required": self.config.require_onnx_models}
            score, method = result
            return {"status": "ok", "score": score, "method": method}
        except Exception as exc:  # noqa: BLE001
            return {"status": "error", "detail": str(exc)}

    def _resolve_minifasnet_path(self) -> Path | None:
        int8_path = self.config.minifasnet_int8_onnx_path
        if int8_path is not None and int8_path.is_file():
            return int8_path
        return self.config.minifasnet_onnx_path

    @staticmethod
    def _is_int8_path(model_path: Path | None) -> bool:
        if model_path is None:
            return False
        name = model_path.name.lower()
        return "int8" in name or "quant" in name

    def _smoke_deepfake(self, image_bgr: np.ndarray) -> dict[str, object]:
        if not self._is_available(self.config.deepfake_onnx_path):
            return {"status": "missing", "required": self.config.require_onnx_models}
        try:
            result = self.run_deepfake(image_bgr)
            if result is None:
                return {"status": "missing", "required": self.config.require_onnx_models}
            score, method = result
            return {"status": "ok", "score": score, "method": method}
        except Exception as exc:  # noqa: BLE001
            return {"status": "error", "detail": str(exc)}

    def _status(self, model_path: Path | None, name: str) -> OnnxModelStatus:
        if model_path is None:
            return OnnxModelStatus(name=name, path=None, available=False, detail="not_configured")
        if not model_path.is_file():
            return OnnxModelStatus(
                name=name,
                path=str(model_path),
                available=False,
                detail="file_missing",
            )
        try:
            session = self._get_session(name, model_path)
            input_meta = session.get_inputs()[0]
            output_meta = session.get_outputs()[0]
            return OnnxModelStatus(
                name=name,
                path=str(model_path),
                available=True,
                input_shape=list(input_meta.shape),
                output_shape=list(output_meta.shape),
            )
        except Exception as exc:  # noqa: BLE001
            return OnnxModelStatus(
                name=name,
                path=str(model_path),
                available=False,
                detail=str(exc),
            )

    @staticmethod
    def _is_available(model_path: Path | None) -> bool:
        return model_path is not None and model_path.is_file()


def _spatial_dims(shape: list[Any], *, default: int = 80) -> tuple[int, int]:
    height = int(shape[2]) if isinstance(shape[2], int) else default
    width = int(shape[3]) if isinstance(shape[3], int) else default
    return height, width


# Backward-compatible aliases for tests and external imports.
_crop_face_minifasnet = crop_face_minifasnet
_to_nchw_float_bgr255 = to_minifasnet_tensor
_minifasnet_live_score = minifasnet_live_score


def _crop_face_with_scale(
    image_bgr: np.ndarray,
    bbox: list[int],
    *,
    scale: float,
    out_size: tuple[int, int],
) -> np.ndarray:
    x, y, w, h = bbox
    cx = x + w / 2.0
    cy = y + h / 2.0
    side = max(w, h) * scale
    half = side / 2.0
    x1 = int(max(0, cx - half))
    y1 = int(max(0, cy - half))
    x2 = int(min(image_bgr.shape[1], cx + half))
    y2 = int(min(image_bgr.shape[0], cy + half))
    crop = image_bgr[y1:y2, x1:x2]
    if crop.size == 0:
        crop = image_bgr[y : y + h, x : x + w]
    return cv2.resize(crop, out_size)


def _to_nchw_float01(image_bgr: np.ndarray) -> np.ndarray:
    rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    return np.transpose(rgb, (2, 0, 1))[None, ...]


def _to_nchw_imagenet(image_bgr: np.ndarray) -> np.ndarray:
    rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    normalized = (rgb - IMAGENET_MEAN) / IMAGENET_STD
    return np.transpose(normalized, (2, 0, 1))[None, ...]


def _softmax(values: np.ndarray) -> np.ndarray:
    shifted = values - np.max(values)
    exp = np.exp(shifted)
    return exp / np.sum(exp)


def _fake_class_index(class_count: int) -> int:
    if class_count <= 1:
        return 0
    return 1 if class_count == 2 else 1


def _vit_pixel_values(face_crop_bgr: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    resized = cv2.resize(face_crop_bgr, size)
    rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    normalized = (rgb - IMAGENET_MEAN) / IMAGENET_STD
    return np.transpose(normalized, (2, 0, 1))[None, ...].astype(np.float32)


def _synthetic_face_image() -> np.ndarray:
    image = np.full((160, 160, 3), 128, dtype=np.uint8)
    cv2.circle(image, (80, 76), 48, (170, 150, 130), -1)
    cv2.circle(image, (62, 68), 5, (40, 40, 40), -1)
    cv2.circle(image, (98, 68), 5, (40, 40, 40), -1)
    cv2.ellipse(image, (80, 92), (18, 8), 0, 0, 180, (50, 50, 50), 2)
    return image


def _clip01(value: float) -> float:
    return max(0.0, min(1.0, value))
