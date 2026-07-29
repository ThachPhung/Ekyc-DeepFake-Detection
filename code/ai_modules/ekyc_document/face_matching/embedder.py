"""InsightFace SCRFD detection + 5-point alignment + ArcFace embedding."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ekyc_document.config import PipelineConfig
from ekyc_document.face_matching.alignment import align_face_insightface, require_landmarks_5
from ekyc_document.face_matching.arcface import resolve_insightface_model
from ekyc_document.face_matching.insightface_loader import create_face_analysis


@dataclass(frozen=True)
class FaceEmbeddingResult:
    bbox: list[int]
    confidence: float
    face_count: int
    embedding: np.ndarray
    aligned_crop: np.ndarray
    landmarks: np.ndarray
    embedding_model: str
    detector: str


class InsightFaceEmbedder:
    """
    Production face embedder:
    SCRFD/RetinaFace detection -> 5-point alignment -> ArcFace L2-normalized vector.
    """

    def __init__(self, config: PipelineConfig | None = None) -> None:
        self.config = config or PipelineConfig()
        self._app = None

    def diagnostics(self) -> dict[str, object]:
        model = resolve_insightface_model(
            self.config.insightface_model,
            profile=self.config.insightface_profile,
        )
        return {
            "detector": self.config.face_detector,
            "detector_backend": "scrfd",
            "alignment": "5_point_landmark",
            "recognition": model,
            "det_size": self.config.insightface_det_size,
            "embedding_dim": 512,
            "normalization": "l2",
            "similarity": "cosine",
        }

    def detect_best(self, image_bgr: np.ndarray) -> FaceEmbeddingResult | None:
        self._ensure_loaded()
        if self._app == "opencv":
            return None

        faces = self._app.get(image_bgr)
        if not faces:
            return None

        best = max(faces, key=lambda face: float(getattr(face, "det_score", 0.0)))
        landmarks = require_landmarks_5(getattr(best, "kps", None))
        if landmarks is None:
            return None

        x1, y1, x2, y2 = [int(v) for v in best.bbox]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(image_bgr.shape[1], x2), min(image_bgr.shape[0], y2)
        bbox = [x1, y1, x2 - x1, y2 - y1]

        aligned = align_face_insightface(
            image_bgr,
            landmarks,
            image_size=self.config.insightface_align_size,
        )

        embedding = getattr(best, "normed_embedding", None)
        if embedding is None:
            embedding = getattr(best, "embedding", None)
        embedding_array = _l2_normalize(embedding)
        if embedding_array is None:
            return None

        model = resolve_insightface_model(
            self.config.insightface_model,
            profile=self.config.insightface_profile,
        )
        return FaceEmbeddingResult(
            bbox=bbox,
            confidence=round(float(getattr(best, "det_score", 0.0)), 4),
            face_count=len(faces),
            embedding=embedding_array,
            aligned_crop=aligned,
            landmarks=landmarks,
            embedding_model=f"insightface/{model}",
            detector="scrfd",
        )

    def _ensure_loaded(self) -> None:
        if self._app is not None:
            return
        self._app = create_face_analysis(self.config)


def _l2_normalize(raw: object) -> np.ndarray | None:
    if raw is None:
        return None
    vector = np.asarray(raw, dtype=np.float32).reshape(-1)
    norm = float(np.linalg.norm(vector))
    if norm <= 0.0:
        return None
    return vector / norm
