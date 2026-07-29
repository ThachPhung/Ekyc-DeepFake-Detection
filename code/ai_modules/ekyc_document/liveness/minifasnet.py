"""MiniFASNet V2 SE passive anti-spoofing integration."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ekyc_document.config import PipelineConfig
from ekyc_document.onnx_models import OnnxModelRegistry


@dataclass(frozen=True)
class MiniFASNetResult:
    score: float
    passed: bool
    method: str
    model_path: str | None = None


class MiniFASNetAntiSpoof:
    """
    Passive liveness via MiniFASNet V2 (ONNX).

    Production target: MiniFASNetV2-SE INT8 (~600KB) for print/replay attacks.
    Current repo ships FP32 `minifasnet.onnx` (~2MB) with the same crop preprocess.
    """

    def __init__(
        self,
        config: PipelineConfig | None = None,
        registry: OnnxModelRegistry | None = None,
    ) -> None:
        self.config = config or PipelineConfig()
        self._registry = registry or OnnxModelRegistry(self.config)

    def diagnostics(self) -> dict[str, object]:
        int8_path = self.config.minifasnet_int8_onnx_path
        fp32_path = self.config.minifasnet_onnx_path
        active = self._active_model_path()
        return {
            "active_model": str(active) if active else None,
            "fp32_path": str(fp32_path),
            "int8_path": str(int8_path) if int8_path else None,
            "crop_scale": self.config.minifasnet_crop_scale,
            "threshold": self.config.min_liveness_score,
            "onnx": self._registry.diagnostics().get("minifasnet"),
        }

    def _active_model_path(self):
        int8_path = self.config.minifasnet_int8_onnx_path
        if int8_path is not None and int8_path.is_file():
            return int8_path
        fp32_path = self.config.minifasnet_onnx_path
        if fp32_path is not None and fp32_path.is_file():
            return fp32_path
        return None

    def score(self, image_bgr: np.ndarray, bbox: list[int]) -> MiniFASNetResult | None:
        model_path = self._active_model_path()
        if model_path is None:
            return None

        if model_path == self.config.minifasnet_int8_onnx_path:
            method = "minifasnet_v2_se_int8"
        else:
            method = "minifasnet_v2_onnx"

        result = self._registry.run_minifasnet(image_bgr, bbox)
        if result is None:
            return None

        live_score, method = result
        return MiniFASNetResult(
            score=live_score,
            passed=live_score >= self.config.min_liveness_score,
            method=method,
            model_path=str(model_path),
        )
