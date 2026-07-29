"""Text line detection — DBNet (PaddleOCR DB++) with RapidOCR det fallback."""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from ekyc_document.config import PipelineConfig


@dataclass(frozen=True)
class TextLineBox:
    polygon: list[list[float]]
    confidence: float


class DBNetDetector:
    def __init__(self, config: PipelineConfig | None = None) -> None:
        self.config = config or PipelineConfig()
        self._paddle = None
        self._rapid = None
        self._backend = self.config.dbnet_backend

    def diagnostics(self) -> dict[str, object]:
        return {
            "backend": self._backend,
            "paddle_available": self._can_use_paddle(),
            "rapid_available": True,
        }

    def _can_use_paddle(self) -> bool:
        try:
            import paddleocr  # noqa: F401

            return True
        except ImportError:
            return False

    def _lazy_init_paddle(self) -> None:
        if self._paddle is not None:
            return
        from paddleocr import PaddleOCR

        self._paddle = PaddleOCR(
            use_angle_cls=False,
            lang="vi",
            det=True,
            rec=False,
            use_gpu=self.config.use_gpu,
            show_log=False,
        )
        self._backend = "paddle_dbnet"

    def _lazy_init_rapid(self) -> None:
        if self._rapid is not None:
            return
        from rapidocr import RapidOCR
        from rapidocr.utils.typings import OCRVersion

        self._rapid = RapidOCR(
            params={
                "Det.ocr_version": OCRVersion.PPOCRV6,
                "Det.lang_type": self.config.rapidocr_lang,
                "Rec.engine_type": None,
                "EngineConfig.onnxruntime.use_cuda": self.config.use_gpu,
            }
        )
        self._backend = "rapidocr_det"

    def detect(self, image: np.ndarray, *, roi: tuple[int, int, int, int] | None = None) -> list[TextLineBox]:
        if roi is not None:
            x1, y1, x2, y2 = roi
            crop = image[y1:y2, x1:x2]
            offset_x, offset_y = float(x1), float(y1)
        else:
            crop = image
            offset_x, offset_y = 0.0, 0.0

        if crop.size == 0:
            return []

        if self.config.dbnet_backend == "paddle" and self._can_use_paddle():
            try:
                self._lazy_init_paddle()
                return self._detect_paddle(crop, offset_x=offset_x, offset_y=offset_y)
            except Exception:
                pass

        self._lazy_init_rapid()
        return self._detect_rapid(crop, offset_x=offset_x, offset_y=offset_y)

    def _detect_paddle(
        self,
        image: np.ndarray,
        *,
        offset_x: float,
        offset_y: float,
    ) -> list[TextLineBox]:
        assert self._paddle is not None
        output = self._paddle.ocr(image, cls=False)
        boxes: list[TextLineBox] = []
        if not output or not output[0]:
            return boxes

        for item in output[0]:
            polygon = [[float(x + offset_x), float(y + offset_y)] for x, y in item[0]]
            boxes.append(TextLineBox(polygon=polygon, confidence=1.0))
        return boxes

    def _detect_rapid(
        self,
        image: np.ndarray,
        *,
        offset_x: float,
        offset_y: float,
    ) -> list[TextLineBox]:
        assert self._rapid is not None
        try:
            result = self._rapid(image, use_det=True, use_cls=False, use_rec=False)
        except TypeError:
            result = self._rapid(image)
        boxes: list[TextLineBox] = []
        if result is None or getattr(result, "boxes", None) is None:
            return boxes

        for bbox in result.boxes:
            polygon = [[float(x + offset_x), float(y + offset_y)] for x, y in bbox]
            boxes.append(TextLineBox(polygon=polygon, confidence=1.0))
        return boxes


def crop_line_image(image: np.ndarray, polygon: list[list[float]], *, padding: int = 4) -> np.ndarray:
    xs = [point[0] for point in polygon]
    ys = [point[1] for point in polygon]
    x1 = max(0, int(min(xs)) - padding)
    y1 = max(0, int(min(ys)) - padding)
    x2 = min(image.shape[1], int(max(xs)) + padding)
    y2 = min(image.shape[0], int(max(ys)) + padding)
    crop = image[y1:y2, x1:x2]
    if crop.size == 0:
        return crop

    angle = _estimate_text_angle(polygon)
    if abs(angle) > 1.0:
        center = ((x1 + x2) / 2, (y1 + y2) / 2)
        matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
        return cv2.warpAffine(image, matrix, (image.shape[1], image.shape[0]))[y1:y2, x1:x2]
    return crop


def _estimate_text_angle(polygon: list[list[float]]) -> float:
    points = np.array(polygon, dtype=np.float32)
    if len(points) < 2:
        return 0.0
    vector = points[1] - points[0]
    return float(np.degrees(np.arctan2(vector[1], vector[0])))
