"""Face detection and extraction from document images."""

from __future__ import annotations

import base64

import cv2
import numpy as np

from ekyc_document.config import PipelineConfig
from ekyc_document.face_matching.insightface_loader import create_face_analysis
from ekyc_document.schemas import FaceResult


class FaceExtractor:
    def __init__(self, config: PipelineConfig | None = None) -> None:
        self.config = config or PipelineConfig()
        self._app = None

    def _lazy_init(self) -> None:
        if self._app is not None:
            return
        self._app = create_face_analysis(self.config)

    def extract(self, image: np.ndarray, include_crop: bool = False) -> FaceResult:
        self._lazy_init()

        if self._app == "opencv":
            return self._extract_opencv(image, include_crop)

        assert self._app is not None
        faces = self._app.get(image)
        if not faces:
            return FaceResult(detected=False)

        # Document photos usually have one portrait; pick highest detection score
        best = max(faces, key=lambda f: float(f.det_score))
        x1, y1, x2, y2 = [int(v) for v in best.bbox]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(image.shape[1], x2), min(image.shape[0], y2)
        bbox = [x1, y1, x2 - x1, y2 - y1]
        crop = image[y1:y2, x1:x2]
        quality_score, confident, warnings = _assess_document_face(
            image=image,
            crop=crop,
            bbox=bbox,
            detection_confidence=float(best.det_score),
            min_confidence=self.config.min_document_face_confidence,
        )

        crop_b64 = None
        if include_crop:
            if crop.size > 0:
                crop_b64 = _encode_image_base64(crop)

        return FaceResult(
            detected=True,
            bbox=bbox,
            confidence=round(float(best.det_score), 4),
            quality_score=quality_score,
            confident=confident,
            warnings=warnings,
            crop_base64=crop_b64,
        )

    def _extract_opencv(self, image: np.ndarray, include_crop: bool) -> FaceResult:
        """Lightweight fallback using OpenCV Haar cascade."""
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        detector = cv2.CascadeClassifier(cascade_path)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        faces = detector.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(40, 40))

        if len(faces) == 0:
            return FaceResult(detected=False)

        x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
        bbox = [int(x), int(y), int(w), int(h)]
        crop = image[y : y + h, x : x + w]
        quality_score, confident, warnings = _assess_document_face(
            image=image,
            crop=crop,
            bbox=bbox,
            detection_confidence=0.6,
            min_confidence=self.config.min_document_face_confidence,
        )
        crop_b64 = None
        if include_crop:
            crop_b64 = _encode_image_base64(crop)

        return FaceResult(
            detected=True,
            bbox=bbox,
            confidence=0.6,
            quality_score=quality_score,
            confident=confident,
            warnings=warnings,
            crop_base64=crop_b64,
        )


def _encode_image_base64(image: np.ndarray) -> str:
    ok, buffer = cv2.imencode(".jpg", image)
    if not ok:
        return ""
    return base64.b64encode(buffer.tobytes()).decode("ascii")


def _clip01(value: float) -> float:
    return float(max(0.0, min(1.0, value)))


def _assess_document_face(
    *,
    image: np.ndarray,
    crop: np.ndarray,
    bbox: list[int],
    detection_confidence: float,
    min_confidence: float,
) -> tuple[float | None, bool, list[str]]:
    if crop.size == 0:
        return 0.0, False, ["Vùng ảnh chân dung trên giấy tờ không hợp lệ."]

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    blur_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    blur = _clip01((blur_var - 25.0) / 175.0)

    mean = float(np.mean(gray))
    if 80.0 <= mean <= 185.0:
        illumination = 1.0
    elif mean < 80.0:
        illumination = _clip01(mean / 80.0)
    else:
        illumination = _clip01((255.0 - mean) / 70.0)

    contrast = _clip01((float(np.std(gray)) - 12.0) / 38.0)

    image_h, image_w = image.shape[:2]
    _, _, face_w, face_h = bbox
    min_side = max(0, min(face_w, face_h))
    size = _clip01((min_side - 45.0) / 115.0)
    coverage = _clip01(((face_w * face_h) / float(image_w * image_h) - 0.01) / 0.09)
    detection = _clip01(detection_confidence)

    score = round(
        detection * 0.30
        + blur * 0.30
        + illumination * 0.15
        + contrast * 0.15
        + max(size, coverage) * 0.10,
        4,
    )

    warnings: list[str] = []
    if detection < 0.55:
        warnings.append("Độ tin cậy phát hiện khuôn mặt trên giấy tờ thấp.")
    if blur < 0.45:
        warnings.append("Ảnh chân dung trên giấy tờ bị mờ, cần chụp lại rõ nét hơn.")
    if illumination < 0.45:
        warnings.append("Ảnh chân dung trên giấy tờ quá tối/quá sáng.")
    if contrast < 0.45:
        warnings.append("Ảnh chân dung trên giấy tờ có độ tương phản thấp.")
    if size < 0.45 and coverage < 0.45:
        warnings.append("Ảnh chân dung trên giấy tờ quá nhỏ, cần chụp gần và rõ hơn.")
    if score < min_confidence:
        warnings.append(
            f"Độ rõ khuôn mặt trên giấy tờ ({score:.2f}) dưới ngưỡng {min_confidence:.2f}."
        )

    return score, score >= min_confidence, warnings
