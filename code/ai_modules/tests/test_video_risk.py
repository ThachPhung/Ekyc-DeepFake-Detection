from __future__ import annotations

import numpy as np

from ekyc_document.biometric import (
    BiometricFace,
    BiometricPipeline,
    FrameFace,
    FrameSample,
    VideoFrameExtraction,
)
from ekyc_document.schemas import (
    ActiveLivenessChallengeResult,
    CameraInjectionResult,
    DeepfakeAnalysisResult,
    FaceMatchingResult,
    FaceQualityDetail,
    PassiveLivenessResult,
    ReplayAttackResult,
    TemporalIdentityConsistencyResult,
)


def _crop(value: int = 128) -> np.ndarray:
    return np.full((96, 96, 3), value, dtype=np.uint8)


def _frame(value: int = 128) -> np.ndarray:
    return np.full((128, 128, 3), value, dtype=np.uint8)


def _frame_face(frame_index: int, embedding: np.ndarray | None = None) -> FrameFace:
    return FrameFace(
        frame_index=frame_index,
        face=BiometricFace(
            bbox=[16, 16, 80, 80],
            confidence=0.99,
            face_count=1,
            embedding=embedding,
            crop=_crop(),
            embedding_model="test/arcface",
        ),
        quality_score=0.82,
        quality=FaceQualityDetail(
            blur=0.9,
            pose=0.9,
            illumination=0.9,
            face_coverage=0.8,
            centered=0.9,
        ),
    )


def test_deepfake_analysis_aggregates_frame_model_scores() -> None:
    pipeline = BiometricPipeline()
    scores = iter([0.2, 0.91, 0.74])
    pipeline._run_deepfake_model = lambda _crop: (next(scores), "test/deepfake")  # type: ignore[method-assign]

    result = pipeline.analyze_deepfake_frames(
        [_frame_face(0), _frame_face(5), _frame_face(10)]
    )

    assert result.mean_score == 0.6167
    assert result.max_score == 0.91
    assert result.suspicious_frame_count == 2
    assert result.suspicious_frames == [5, 10]
    assert result.score > 0.6


def test_temporal_identity_consistency_flags_embedding_drift() -> None:
    pipeline = BiometricPipeline()
    stable = np.asarray([1.0, 0.0], dtype=np.float32)
    mild = np.asarray([0.98, 0.2], dtype=np.float32)
    mild = mild / np.linalg.norm(mild)
    swapped = np.asarray([0.0, 1.0], dtype=np.float32)

    result = pipeline.temporal_identity_consistency(
        [_frame_face(0, stable), _frame_face(5, mild), _frame_face(10, swapped)]
    )

    assert result.embedding_frames == 3
    assert result.max_drift is not None
    assert result.max_drift > pipeline.config.identity_drift_threshold
    assert result.suspicious_pair_count == 1
    assert result.score >= pipeline.config.video_risk_review_threshold


def test_replay_attack_heuristics_flags_duplicated_frames() -> None:
    pipeline = BiometricPipeline()
    samples = [
        FrameSample(frame_index=index, timestamp_ms=index * 100.0, frame=_frame(90))
        for index in range(6)
    ]

    result = pipeline.replay_attack_heuristics(samples)

    assert result.duplicate_pairs == 5
    assert result.duplication_score == 1.0
    assert result.confirmed is True
    assert result.score >= pipeline.config.replay_suspicious_threshold


def test_replay_attack_heuristics_does_not_confirm_static_natural_motion() -> None:
    pipeline = BiometricPipeline()
    samples = []
    for index in range(6):
        frame = _frame(90)
        noise = np.random.default_rng(index).integers(0, 8, frame.shape, dtype=np.uint8)
        frame = np.clip(frame.astype(np.int16) + noise, 0, 255).astype(np.uint8)
        samples.append(FrameSample(frame_index=index, timestamp_ms=index * 100.0, frame=frame))

    result = pipeline.replay_attack_heuristics(samples)

    assert result.confirmed is False
    assert result.score < pipeline.config.replay_suspicious_threshold


def test_camera_injection_heuristics_uses_metadata_timing_and_duplication() -> None:
    pipeline = BiometricPipeline()
    samples = [
        FrameSample(frame_index=index, timestamp_ms=None, frame=_frame(100))
        for index in range(4)
    ]
    extraction = VideoFrameExtraction(
        samples=samples,
        fps=None,
        frame_count=None,
        duration_ms=500.0,
    )
    replay = pipeline.replay_attack_heuristics(samples)

    result = pipeline.camera_injection_heuristics(
        extraction=extraction,
        active_results=[
            ActiveLivenessChallengeResult(
                challenge="blink",
                passed=False,
                confidence=0.0,
            )
        ],
        replay=replay,
    )

    assert result.metadata_score == 1.0
    assert result.challenge_timing_score >= 0.9
    assert result.duplication_score == 1.0
    assert result.score >= pipeline.config.camera_injection_suspicious_threshold


def test_decision_fails_when_video_risk_is_blocking() -> None:
    pipeline = BiometricPipeline()
    samples = [
        FrameSample(frame_index=index, timestamp_ms=None, frame=_frame(100))
        for index in range(5)
    ]
    risk = pipeline.assess_video_risk(
        extraction=VideoFrameExtraction(
            samples=samples,
            fps=None,
            frame_count=None,
            duration_ms=400.0,
        ),
        frame_faces=[],
        active_results=[
            ActiveLivenessChallengeResult(
                challenge="blink",
                passed=False,
                confidence=0.0,
            )
        ],
    )

    blocking_risk = risk.model_copy(
        update={
            "score": pipeline.config.video_risk_block_threshold,
            "decision": "failed",
        }
    )

    decision = pipeline.decide(
        matching=FaceMatchingResult(
            similarity=0.9,
            decision="match",
            thresholds={"match": 0.6, "consider": 0.4},
            reason="test",
        ),
        quality_score=0.9,
        passive_liveness=PassiveLivenessResult(
            score=0.9,
            passed=True,
            method="test",
        ),
        portrait_ok=True,
        active_passed=True,
        risk=blocking_risk,
    )

    assert blocking_risk.score >= pipeline.config.video_risk_block_threshold
    assert decision == "failed"


def test_video_risk_uses_configurable_weights_and_evidence() -> None:
    pipeline = BiometricPipeline()
    pipeline.config.video_risk_weights = {
        "deepfake": 0.80,
        "identity": 0.10,
        "replay": 0.05,
        "camera": 0.05,
    }
    pipeline.analyze_deepfake_frames = lambda _frame_faces: DeepfakeAnalysisResult(  # type: ignore[method-assign]
        score=0.8,
        mean_score=0.7,
        max_score=0.9,
        suspicious_frame_count=1,
        suspicious_frames=[0],
        method="test",
    )
    pipeline.temporal_identity_consistency = lambda _frame_faces: TemporalIdentityConsistencyResult(  # type: ignore[method-assign]
        score=0.2,
        mean_drift=0.05,
        max_drift=0.1,
        suspicious_pair_count=0,
        embedding_frames=2,
        method="test",
    )
    pipeline.replay_attack_heuristics = lambda _samples: ReplayAttackResult(  # type: ignore[method-assign]
        score=0.1,
        moire_score=0.0,
        flicker_score=0.0,
        duplication_score=0.1,
        duplicate_pairs=0,
    )
    pipeline.camera_injection_heuristics = lambda **_kwargs: CameraInjectionResult(  # type: ignore[method-assign]
        score=0.0,
        metadata_score=0.0,
        challenge_timing_score=0.0,
        duplication_score=0.0,
    )

    risk = pipeline.assess_video_risk(
        extraction=VideoFrameExtraction(
            samples=[FrameSample(frame_index=0, timestamp_ms=0.0, frame=_frame())],
            fps=30.0,
            frame_count=1,
            duration_ms=33.3,
        ),
        frame_faces=[_frame_face(0, np.asarray([1.0, 0.0], dtype=np.float32))],
        active_results=[
            ActiveLivenessChallengeResult(
                challenge="blink",
                passed=True,
                confidence=0.9,
            )
        ],
    )

    deepfake_evidence = next(item for item in risk.evidence if item.signal == "deepfake")
    assert risk.weights == {
        "deepfake": 0.8,
        "identity": 0.1,
        "replay": 0.05,
        "camera": 0.05,
    }
    assert risk.score == 0.665
    assert deepfake_evidence.contribution == 0.64
    assert deepfake_evidence.triggered is True
    assert risk.reason_codes == ["deepfake_frames"]
    assert risk.top_reasons[0].reason_code == "deepfake_frames"
    assert risk.top_reasons[0].signal == "deepfake"


def test_assess_video_risk_includes_lipsync_signal_when_service_returns_fake() -> None:
    from unittest.mock import patch

    from ekyc_document.config import PipelineConfig
    from ekyc_document.lipsync_client import LipSyncServiceResponse

    pipeline = BiometricPipeline(
        PipelineConfig(
            lipsync_service_url="http://lipsync-deepfake:8002",
            lipsync_enabled=True,
        )
    )
    pipeline.analyze_deepfake_frames = lambda _faces: DeepfakeAnalysisResult(  # type: ignore[method-assign]
        score=0.0,
        mean_score=0.0,
        max_score=0.0,
        suspicious_frame_count=0,
        method="test",
    )
    pipeline.temporal_identity_consistency = lambda _faces: TemporalIdentityConsistencyResult(  # type: ignore[method-assign]
        score=0.0,
        embedding_frames=0,
        method="test",
    )
    pipeline.replay_attack_heuristics = lambda _samples: ReplayAttackResult(  # type: ignore[method-assign]
        score=0.0,
        moire_score=0.0,
        flicker_score=0.0,
        duplication_score=0.0,
    )
    pipeline.camera_injection_heuristics = lambda **_kwargs: CameraInjectionResult(  # type: ignore[method-assign]
        score=0.0,
        metadata_score=0.0,
        challenge_timing_score=0.0,
        duplication_score=0.0,
    )

    fake_response = LipSyncServiceResponse(
        verdict="fake",
        is_fake=True,
        is_real=False,
        confidence=0.1,
        manipulation_probability=0.9,
    )

    with patch(
        "ekyc_document.biometric.request_lipsync_analysis",
        return_value=fake_response,
    ):
        risk = pipeline.assess_video_risk(
            extraction=VideoFrameExtraction(
                samples=[FrameSample(frame_index=0, timestamp_ms=0.0, frame=_frame())],
                fps=30.0,
                frame_count=1,
                duration_ms=33.3,
            ),
            frame_faces=[],
            active_results=[
                ActiveLivenessChallengeResult(
                    challenge="blink",
                    passed=True,
                    confidence=0.9,
                )
            ],
            video_bytes=b"fake-video-bytes",
        )

    lipsync_evidence = next(item for item in risk.evidence if item.signal == "lipsync")
    assert risk.lipsync is not None
    assert risk.lipsync.verdict == "fake"
    assert lipsync_evidence.triggered is True
    assert "lipsync_deepfake" in risk.reason_codes

