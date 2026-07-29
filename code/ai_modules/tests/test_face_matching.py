from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np

from ekyc_document.biometric import BiometricFace, BiometricPipeline
from ekyc_document.config import PipelineConfig
from ekyc_document.face_matching.arcface import (
    ArcFaceMatcher,
    cosine_similarity,
    resolve_insightface_model,
)
from ekyc_document.face_matching.embedder import FaceEmbeddingResult


def _face(embedding: np.ndarray | None) -> BiometricFace:
    return BiometricFace(
        bbox=[10, 10, 90, 90],
        confidence=0.99,
        face_count=1,
        embedding=embedding,
        crop=np.zeros((80, 80, 3), dtype=np.uint8),
        embedding_model="test/arcface",
    )


def test_cosine_similarity_for_identical_vectors() -> None:
    vector = np.asarray([1.0, 0.0, 0.0], dtype=np.float32)
    assert cosine_similarity(vector, vector) == 1.0


def test_arcface_match_decision() -> None:
    matcher = ArcFaceMatcher(PipelineConfig())
    doc = _face(np.asarray([1.0, 0.0, 0.0], dtype=np.float32))
    live = _face(np.asarray([0.98, 0.2, 0.0], dtype=np.float32))

    result = matcher.compare(doc, live)

    assert result.decision == "match"
    assert result.similarity is not None
    assert result.similarity >= matcher.config.face_match_threshold


def test_arcface_consider_without_embedding() -> None:
    matcher = ArcFaceMatcher(PipelineConfig())
    result = matcher.compare(_face(None), _face(None))
    assert result.decision == "consider"
    assert result.similarity is None


def test_resolve_insightface_model_profile() -> None:
    assert resolve_insightface_model(None, profile="speed") == "buffalo_l"
    assert resolve_insightface_model(None, profile="accuracy") == "glintr100"


def test_arcface_diagnostics_lists_supported_models() -> None:
    diagnostics = ArcFaceMatcher(PipelineConfig()).diagnostics()
    assert diagnostics["algorithm"] == "arcface"
    assert "buffalo_l" in diagnostics["supported_models"]
    assert "glintr100" in diagnostics["supported_models"]


def test_detect_best_face_lazy_inits_embedder(monkeypatch) -> None:
    pipeline = BiometricPipeline(PipelineConfig())
    assert pipeline._face_embedder is None

    embedding = np.asarray([1.0, 0.0, 0.0], dtype=np.float32)
    mock_embedder = MagicMock()
    mock_embedder.detect_best.return_value = FaceEmbeddingResult(
        bbox=[10, 10, 90, 90],
        confidence=0.99,
        face_count=1,
        embedding=embedding,
        aligned_crop=np.zeros((112, 112, 3), dtype=np.uint8),
        landmarks=np.zeros((5, 2), dtype=np.float32),
        embedding_model="test/arcface",
        detector="scrfd",
    )
    monkeypatch.setattr(
        "ekyc_document.biometric.InsightFaceEmbedder",
        lambda config: mock_embedder,
    )

    image = np.zeros((200, 200, 3), dtype=np.uint8)
    face = pipeline.detect_best_face(image)

    assert pipeline._face_embedder is mock_embedder
    mock_embedder.detect_best.assert_called_once_with(image)
    assert isinstance(face, BiometricFace)
    assert face.embedding is not None
