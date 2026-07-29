"""InsightFace ArcFace 1:1 face matching helpers."""

from __future__ import annotations

from typing import Protocol

import numpy as np

from ekyc_document.config import PipelineConfig
from ekyc_document.schemas import DecisionType, FaceMatchingResult

INSIGHTFACE_ARCFACE_MODELS: dict[str, dict[str, object]] = {
    "buffalo_l": {
        "profile": "speed",
        "description": "Tốc độ cao — mặc định production eKYC",
        "embedding_dim": 512,
    },
    "buffalo_m": {
        "profile": "balanced",
        "description": "Cân bằng tốc độ/chính xác",
        "embedding_dim": 512,
    },
    "buffalo_s": {
        "profile": "edge",
        "description": "Nhẹ cho edge/mobile server",
        "embedding_dim": 512,
    },
    "glintr100": {
        "profile": "accuracy",
        "description": "Độ chính xác cực cao — ArcFace GlintR100",
        "embedding_dim": 512,
    },
}


class EmbeddingFaceLike(Protocol):
    embedding: np.ndarray | None

    @property
    def embedding_ready(self) -> bool:
        ...


class ArcFaceMatcher:
    """Compare ArcFace embeddings from InsightFace (cosine similarity on L2-normalized vectors)."""

    def __init__(self, config: PipelineConfig | None = None) -> None:
        self.config = config or PipelineConfig()

    def diagnostics(self) -> dict[str, object]:
        model = self.config.insightface_model
        profile = INSIGHTFACE_ARCFACE_MODELS.get(model, {})
        model_root = self.config.models_dir / "models" / model
        return {
            "algorithm": "arcface",
            "detector": self.config.face_detector,
            "model": model,
            "profile": profile.get("profile", "custom"),
            "description": profile.get("description"),
            "embedding_dim": profile.get("embedding_dim", 512),
            "supported_models": sorted(INSIGHTFACE_ARCFACE_MODELS.keys()),
            "model_cached": model_root.is_dir(),
            "alignment": "5_point_landmark",
            "normalization": "l2",
            "metric": "cosine_similarity",
            "thresholds": {
                "match": self.config.face_match_threshold,
                "consider": self.config.face_consider_threshold,
                "max_cosine_distance_match": round(
                    1.0 - self.config.face_match_threshold,
                    4,
                ),
            },
        }

    def compare(
        self,
        doc_face: EmbeddingFaceLike | None,
        live_face: EmbeddingFaceLike | None,
    ) -> FaceMatchingResult:
        thresholds = {
            "match": self.config.face_match_threshold,
            "consider": self.config.face_consider_threshold,
        }
        if doc_face is None or live_face is None:
            return FaceMatchingResult(
                similarity=None,
                decision="failed",
                thresholds=thresholds,
                reason="Thiếu khuôn mặt giấy tờ hoặc khuôn mặt live để so khớp.",
            )
        if not doc_face.embedding_ready or not live_face.embedding_ready:
            return FaceMatchingResult(
                similarity=None,
                decision="consider",
                thresholds=thresholds,
                reason=(
                    "Không có embedding ArcFace; cần cấu hình InsightFace "
                    f"({self.config.insightface_model})."
                ),
            )

        similarity = cosine_similarity(doc_face.embedding, live_face.embedding)
        if similarity >= self.config.face_match_threshold:
            decision: DecisionType = "match"
            reason = "Độ tương đồng ArcFace đạt ngưỡng match."
        elif similarity >= self.config.face_consider_threshold:
            decision = "consider"
            reason = "Độ tương đồng ArcFace nằm trong vùng cần backend xem xét."
        else:
            decision = "failed"
            reason = "Độ tương đồng ArcFace dưới ngưỡng failed."

        return FaceMatchingResult(
            similarity=round(similarity, 4),
            decision=decision,
            thresholds=thresholds,
            reason=reason,
        )


def l2_normalize(vector: np.ndarray | None) -> np.ndarray | None:
    if vector is None:
        return None
    values = np.asarray(vector, dtype=np.float32).reshape(-1)
    norm = float(np.linalg.norm(values))
    if norm <= 0.0:
        return None
    return values / norm


def cosine_similarity(
    left: np.ndarray | None,
    right: np.ndarray | None,
) -> float:
    if left is None or right is None:
        return 0.0
    left_norm = l2_normalize(left)
    right_norm = l2_normalize(right)
    if left_norm is None or right_norm is None:
        return 0.0
    return float(np.dot(left_norm, right_norm))


def cosine_distance(left: np.ndarray | None, right: np.ndarray | None) -> float:
    return round(1.0 - cosine_similarity(left, right), 4)


def resolve_insightface_model(raw: str | None, *, profile: str | None = None) -> str:
    if profile:
        normalized = profile.strip().lower()
        if normalized in {"speed", "fast", "buffalo_l"}:
            return "buffalo_l"
        if normalized in {"accuracy", "accurate", "glintr100", "high"}:
            return "glintr100"

    model = (raw or "buffalo_l").strip()
    if model not in INSIGHTFACE_ARCFACE_MODELS:
        return model
    return model
