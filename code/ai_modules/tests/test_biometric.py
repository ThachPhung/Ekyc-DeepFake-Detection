from __future__ import annotations

import numpy as np

from ekyc_document.biometric import BiometricFace, BiometricPipeline
from ekyc_document.config import PipelineConfig
from ekyc_document.schemas import PassiveLivenessResult


def _face(embedding: np.ndarray | None) -> BiometricFace:
    return BiometricFace(
        bbox=[20, 20, 120, 140],
        confidence=0.99,
        face_count=1,
        embedding=embedding,
        crop=np.zeros((140, 120, 3), dtype=np.uint8),
        embedding_model="test",
    )


def test_face_matching_match_decision() -> None:
    pipeline = BiometricPipeline()
    doc = _face(np.asarray([1.0, 0.0, 0.0], dtype=np.float32))
    live = _face(np.asarray([0.98, 0.2, 0.0], dtype=np.float32))

    result = pipeline.match_faces(doc, live)

    assert result.decision == "match"
    assert result.similarity is not None
    assert result.similarity >= pipeline.config.face_match_threshold


def test_face_matching_consider_decision() -> None:
    pipeline = BiometricPipeline()
    doc = _face(np.asarray([1.0, 0.0, 0.0], dtype=np.float32))
    live = _face(np.asarray([0.5, 0.866, 0.0], dtype=np.float32))

    result = pipeline.match_faces(doc, live)

    assert result.decision == "consider"
    assert result.similarity is not None
    assert pipeline.config.face_consider_threshold <= result.similarity < pipeline.config.face_match_threshold


def test_face_matching_consider_without_embedding() -> None:
    pipeline = BiometricPipeline()

    result = pipeline.match_faces(_face(None), _face(None))

    assert result.decision == "consider"
    assert result.similarity is None


def test_face_matching_failed_decision() -> None:
    pipeline = BiometricPipeline()
    doc = _face(np.asarray([1.0, 0.0, 0.0], dtype=np.float32))
    live = _face(np.asarray([0.2, 0.98, 0.0], dtype=np.float32))

    result = pipeline.match_faces(doc, live)

    assert result.decision == "failed"
    assert result.similarity is not None
    assert result.similarity < pipeline.config.face_consider_threshold


def test_decision_fails_failed_portrait() -> None:
    pipeline = BiometricPipeline()
    matching = pipeline.match_faces(
        _face(np.asarray([1.0, 0.0], dtype=np.float32)),
        _face(np.asarray([1.0, 0.0], dtype=np.float32)),
    )
    liveness = PassiveLivenessResult(score=0.9, passed=True, method="test")

    decision = pipeline.decide(
        matching=matching,
        quality_score=0.9,
        passive_liveness=liveness,
        portrait_ok=False,
    )

    assert decision == "failed"


def test_default_challenge_is_deterministic_blink() -> None:
    pipeline = BiometricPipeline()

    assert pipeline.default_challenge() == "blink"


def test_default_challenge_falls_back_to_blink_when_invalid() -> None:
    pipeline = BiometricPipeline(
        PipelineConfig(default_liveness_challenge="unsupported")
    )

    assert pipeline.default_challenge() == "blink"


def test_active_liveness_runs_by_default() -> None:
    pipeline = BiometricPipeline(PipelineConfig())

    results = pipeline.resolve_active_liveness([], "blink")

    assert len(results) == 1
    assert results[0].passed is False
    assert results[0].confidence == 0.0


def test_skip_active_liveness_always_passes() -> None:
    pipeline = BiometricPipeline(PipelineConfig(skip_active_liveness=True))

    results = pipeline.resolve_active_liveness([], "blink")

    assert len(results) == 1
    assert results[0].passed is True
    assert results[0].confidence == 1.0


def test_passive_liveness_reuses_cached_model(monkeypatch) -> None:
    created = []

    class FakeLivenessModel:
        def __init__(self, config, *, registry):
            created.append(registry)

        def score(self, _image, _bbox):
            return None

    pipeline = BiometricPipeline(
        PipelineConfig(
            minifasnet_onnx_path=None,
            minifasnet_int8_onnx_path=None,
            allow_heuristic_fallback=True,
        )
    )
    monkeypatch.setattr(
        "ekyc_document.biometric.MiniFASNetAntiSpoof",
        FakeLivenessModel,
    )
    image = np.zeros((180, 180, 3), dtype=np.uint8)
    face = _face(np.asarray([1.0, 0.0], dtype=np.float32))

    first = pipeline.passive_liveness(image, face, quality_score=0.8)
    second = pipeline.passive_liveness(image, face, quality_score=0.8)

    assert first.method == "heuristic_fallback"
    assert second.method == "heuristic_fallback"
    assert len(created) == 1
    assert created[0] is pipeline.onnx_registry
