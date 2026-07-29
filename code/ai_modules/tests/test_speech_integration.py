from __future__ import annotations

import numpy as np

from ekyc_document.biometric import BiometricPipeline, FrameFace, FrameSample, VideoFrameExtraction
from ekyc_document.config import PipelineConfig
from ekyc_document.schemas import (
    ActiveLivenessChallengeResult,
    VoiceChallengeResult,
)


def test_assess_video_risk_includes_voice_signal_when_provided() -> None:
    pipeline = BiometricPipeline()
    voice = VoiceChallengeResult(
        expected_text="toi xac nhan",
        transcript="toi xac nhan sai",
        normalized_expected="toi xac nhan",
        normalized_transcript="toi xac nhan sai",
        wer=0.5,
        similarity=0.5,
        passed=False,
        decision="failed",
        audio_detected=True,
        method="test/mock",
    )
    risk = pipeline.assess_video_risk(
        extraction=VideoFrameExtraction(
            samples=[FrameSample(frame_index=0, timestamp_ms=0.0, frame=np.zeros((8, 8, 3), dtype=np.uint8))],
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
        voice=voice,
    )
    voice_evidence = next(item for item in risk.evidence if item.signal == "voice")
    assert voice_evidence.reason_code == "voice_mismatch"
    assert voice_evidence.triggered is True
    assert "voice" in risk.weights


def test_decide_fails_when_voice_decision_failed() -> None:
    from ekyc_document.schemas import FaceMatchingResult, PassiveLivenessResult

    pipeline = BiometricPipeline()
    decision = pipeline.decide(
        matching=FaceMatchingResult(
            similarity=0.9,
            decision="match",
            thresholds={"match": 0.6, "consider": 0.4},
            reason="ok",
        ),
        quality_score=0.9,
        passive_liveness=PassiveLivenessResult(score=0.9, passed=True, method="test"),
        portrait_ok=True,
        voice_decision="failed",
    )
    assert decision == "failed"
