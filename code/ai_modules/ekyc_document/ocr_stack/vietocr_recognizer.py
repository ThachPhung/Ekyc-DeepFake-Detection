"""VietOCR text recognition (CNN + Transformer)."""

from __future__ import annotations

import numpy as np
from PIL import Image

from ekyc_document.config import PipelineConfig


class VietOCRRecognizer:
    def __init__(self, config: PipelineConfig | None = None) -> None:
        self.config = config or PipelineConfig()
        self._predictor = None
        self._ready = False
        self._error: str | None = None

    def diagnostics(self) -> dict[str, object]:
        return {
            "ready": self.is_ready(),
            "config_name": self.config.vietocr_config_name,
            "weights": str(self.config.vietocr_weights)
            if self.config.vietocr_weights
            else None,
            "error": self._error,
        }

    def is_ready(self) -> bool:
        if self._ready:
            return True
        try:
            self._lazy_init()
            return self._ready
        except Exception as exc:  # noqa: BLE001
            self._error = str(exc)
            return False

    def _lazy_init(self) -> None:
        if self._predictor is not None:
            return

        from vietocr.tool.config import Cfg
        from vietocr.tool.predictor import Predictor

        cfg = Cfg.load_config_from_name(self.config.vietocr_config_name)
        cfg["device"] = "cuda:0" if self.config.use_gpu else "cpu"
        cfg["predictor"]["beamsearch"] = False

        if self.config.vietocr_weights and self.config.vietocr_weights.is_file():
            cfg["weights"] = str(self.config.vietocr_weights)

        cfg["cnn"]["pretrained"] = False
        cfg["predictor"]["transform"] = cfg["predictor"].get("transform", "transforms.Compose([])")
        self._predictor = Predictor(cfg)
        self._ready = True

    def recognize(self, image_bgr: np.ndarray) -> tuple[str, float]:
        if image_bgr is None or image_bgr.size == 0:
            return "", 0.0

        self._lazy_init()
        assert self._predictor is not None

        rgb = image_bgr[:, :, ::-1]
        pil_image = Image.fromarray(rgb)
        text = self._predictor.predict(pil_image).strip()
        confidence = 0.92 if text else 0.0
        return text, confidence

    def recognize_batch(self, images: list[np.ndarray]) -> list[tuple[str, float]]:
        return [self.recognize(image) for image in images]
