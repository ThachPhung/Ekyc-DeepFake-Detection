from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from api import main as ai_api
from ekyc_document.schemas import (
    ActiveLivenessChallengeResult,
    CameraInjectionResult,
    DecisionReason,
    DeepfakeAnalysisResult,
    DocumentAnalysisResult,
    FaceDetectionDetail,
    FaceMatchingResult,
    FaceQualityDetail,
    PassiveLivenessResult,
    ReplayAttackResult,
    RiskSignalEvidence,
    TemporalIdentityConsistencyResult,
    VideoRiskResult,
    VideoUploadResult,
    VoiceChallengeResult,
)


def test_health_exposes_ai_runtime_config() -> None:
    response = TestClient(ai_api.app).get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] in {"ok", "degraded", "unhealthy"}
    assert payload["ocr_engine"].startswith("rapidocr")
    assert "risk_weights" in payload
    assert "video_sampling" in payload
    assert "speech" in payload
    assert "onnx" in payload
    assert "onnx_smoke" in payload


def test_voice_challenge_returns_expected_text() -> None:
    response = TestClient(ai_api.app).get("/api/v1/voice/challenge", params={"seed": 7})
    assert response.status_code == 200
    payload = response.json()
    assert payload["expected_text"]
    assert payload["instruction"]
    assert len(payload["numeric_code"]) == 8


def test_voice_verify_failed_digits_returns_reason_codes(monkeypatch, tmp_path: Path) -> None:
    saved_payloads = []

    class _FailingSpeechVerifier:
        def verify_video(self, _content: bytes, expected_text: str) -> VoiceChallengeResult:
            return VoiceChallengeResult(
                expected_text=expected_text,
                transcript="mot hai ba bon",
                normalized_expected="mot hai ba nam",
                normalized_transcript="mot hai ba bon",
                wer=0.25,
                similarity=0.75,
                passed=False,
                decision="failed",
                audio_detected=True,
                method="test",
                warnings=["Spoken digits did not match the challenge."],
            )

    monkeypatch.setattr(ai_api, "get_speech_verifier", lambda: _FailingSpeechVerifier())
    monkeypatch.setattr(
        ai_api,
        "get_private_store",
        lambda: _FakePrivateStore(tmp_path, saved_payloads=saved_payloads),
    )

    response = TestClient(ai_api.app).post(
        "/api/v1/voice/verify",
        files={"file": ("live.mp4", b"video-bytes", "video/mp4")},
        data={"expected_text": "mot hai ba nam"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert payload["decision"] == "failed"
    assert payload["voice_decision"] == "failed"
    assert payload["voice_passed"] is False
    assert payload["voice_wer"] == 0.25
    assert payload["reason_codes"] == ["voice_mismatch"]
    assert payload["decision_reasons"] == ["voice_mismatch"]
    assert payload["expected_text"] == "mot hai ba nam"
    assert payload["transcript"] == "mot hai ba bon"
    assert payload["normalized_expected"] == "mot hai ba nam"
    assert payload["normalized_transcript"] == "mot hai ba bon"
    assert payload["wer"] == 0.25
    assert payload["passed"] is False
    assert payload["method"] == "test"
    assert payload["warnings"] == ["Spoken digits did not match the challenge."]
    assert saved_payloads[0]["decision"] == "failed"


def test_extract_voice_payload_scopes_top_level_voice_fields() -> None:
    payload = {
        "success": False,
        "decision": "failed",
        "record_id": "rec-1",
        "expected_text": "mot hai ba nam",
        "transcript": "mot hai ba bon",
        "normalized_expected": "mot hai ba nam",
        "normalized_transcript": "mot hai ba bon",
        "wer": 0.25,
        "similarity": 0.75,
        "passed": False,
        "audio_detected": True,
        "audio_duration_ms": 1200.0,
        "audio_rms": 0.18,
        "speech_ratio": 0.82,
        "method": "test",
        "warnings": ["Spoken digits did not match the challenge."],
    }

    voice = ai_api._extract_voice_payload(payload)

    assert voice is not None
    assert voice["decision"] == "failed"
    assert voice["passed"] is False
    assert voice["wer"] == 0.25
    assert "record_id" not in voice
    assert "success" not in voice


def test_video_upload_accepts_expected_text(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    class _CapturingPipeline(_FakeBiometricPipeline):
        def analyze_video(self, *_args, **kwargs) -> VideoUploadResult:
            captured.update(kwargs)
            return super().analyze_video()

    monkeypatch.setattr(ai_api, "get_biometric_pipeline", lambda: _CapturingPipeline())
    monkeypatch.setattr(ai_api, "get_private_store", lambda: _FakePrivateStore(tmp_path))

    response = TestClient(ai_api.app).post(
        "/api/v1/video/upload",
        files={
            "file": ("live.mp4", b"video-bytes", "video/mp4"),
            "doc_face": ("front.jpg", b"image-bytes", "image/jpeg"),
        },
        data={"expected_text": "Tôi xác nhận danh tính"},
    )

    assert response.status_code == 200
    assert captured["expected_text"] == "Tôi xác nhận danh tính"


def test_video_upload_accepts_client_frame_metadata(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    class _CapturingPipeline(_FakeBiometricPipeline):
        def analyze_video(self, *_args, **kwargs) -> VideoUploadResult:
            captured.update(kwargs)
            return super().analyze_video()

    monkeypatch.setattr(ai_api, "get_biometric_pipeline", lambda: _CapturingPipeline())
    monkeypatch.setattr(ai_api, "get_private_store", lambda: _FakePrivateStore(tmp_path))

    response = TestClient(ai_api.app).post(
        "/api/v1/video/upload",
        files={
            "file": ("live.mp4", b"video-bytes", "video/mp4"),
            "doc_face": ("front.jpg", b"image-bytes", "image/jpeg"),
        },
        data={
            "best_frame_progress": "0.62",
            "best_frame_index": "12",
            "client_frame_scores": '[{"frame_index":0,"score":0.7,"progress":0.1}]',
        },
    )

    assert response.status_code == 200
    assert captured["client_best_frame_progress"] == 0.62
    assert captured["client_best_frame_index"] == 12
    assert len(captured["client_frame_metrics"]) == 1


def test_video_upload_returns_compact_private_record(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(ai_api, "get_biometric_pipeline", lambda: _FakeBiometricPipeline())
    monkeypatch.setattr(ai_api, "get_private_store", lambda: _FakePrivateStore(tmp_path))

    response = TestClient(ai_api.app).post(
        "/api/v1/video/upload",
        files={
            "file": ("live.mp4", b"video-bytes", "video/mp4"),
            "doc_face": ("front.jpg", b"image-bytes", "image/jpeg"),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["decision"] == "consider"
    assert payload["risk_score"] == 0.52
    assert payload["reason_codes"] == ["deepfake_frames"]
    assert payload["decision_reasons"] == ["video_risk_review"]
    assert "top_reasons" in payload
    assert payload["record_id"] == "test-record-id"


def test_full_verify_saves_ai_summary_and_timings(monkeypatch, tmp_path: Path) -> None:
    saved_payloads = []
    store = _FakePrivateStore(tmp_path, saved_payloads=saved_payloads)
    monkeypatch.setattr(ai_api, "get_pipeline", lambda: _FakeDocumentPipeline())
    monkeypatch.setattr(ai_api, "get_biometric_pipeline", lambda: _FakeBiometricPipeline())
    monkeypatch.setattr(ai_api, "get_private_store", lambda: store)

    response = TestClient(ai_api.app).post(
        "/api/v1/ekyc/verify",
        files={
            "front_file": ("front.jpg", b"front", "image/jpeg"),
            "back_file": ("back.jpg", b"back", "image/jpeg"),
            "video_file": ("live.mp4", b"video", "video/mp4"),
        },
        data={"document_type": "CCCD"},
    )

    assert response.status_code == 200
    assert response.json()["risk_score"] == 0.52
    saved = saved_payloads[0]
    assert saved["ai_summary"]["document"]["document_face_confident"] is True
    assert saved["ai_summary"]["risk"]["evidence"][0]["signal"] == "deepfake"
    assert "decision_reasons" in saved["ai_summary"]["biometric"]
    assert "top_reasons" in saved["ai_summary"]["risk"]
    assert saved["timings_ms"]["document_total"] == 11.0
    assert saved["timings_ms"]["video_total"] == 22.0


class _FakeDocumentPipeline:
    def analyze_two_sides(self, *_args, **_kwargs) -> DocumentAnalysisResult:
        return DocumentAnalysisResult(
            document_type="CCCD",
            ocr_confidence=0.93,
            image_quality_score=0.88,
            document_face_detected=True,
            document_face_confident=True,
            document_face_confidence=0.91,
            timings_ms={"total": 11.0},
        )


class _FakeBiometricPipeline:
    def analyze_video(self, *_args, **_kwargs) -> VideoUploadResult:
        return VideoUploadResult(
            success=False,
            decision="consider",
            frames_analyzed=12,
            face_frames=12,
            best_live_face=FaceDetectionDetail(
                detected=True,
                face_count=1,
                confidence=0.97,
                embedding_ready=True,
                portrait_ok=True,
            ),
            quality_score=0.84,
            quality_details=FaceQualityDetail(
                blur=0.9,
                pose=0.8,
                illumination=0.8,
                face_coverage=0.7,
                centered=0.9,
            ),
            passive_liveness=PassiveLivenessResult(
                score=0.86,
                passed=True,
                method="test",
            ),
            active_liveness=[
                ActiveLivenessChallengeResult(
                    challenge="blink",
                    passed=True,
                    confidence=0.9,
                )
            ],
            matching=FaceMatchingResult(
                similarity=0.72,
                decision="match",
                thresholds={"match": 0.6, "consider": 0.4},
                reason="test",
            ),
            risk=_risk_result(),
            decision_reasons=[
                DecisionReason(
                    code="video_risk_review",
                    message="Risk engine vượt ngưỡng cần review.",
                    severity="warning",
                )
            ],
            timings_ms={"total": 22.0, "risk": 5.0},
        )


class _FakePrivateStore:
    def __init__(self, tmp_path: Path, saved_payloads: list | None = None) -> None:
        self.tmp_path = tmp_path
        self.saved_payloads = saved_payloads

    def save_result_record(self, *, record_type: str, payload: dict) -> tuple[str, Path]:
        if self.saved_payloads is not None:
            self.saved_payloads.append(payload)
        return "test-record-id", self.tmp_path / f"{record_type}.json"


def _risk_result() -> VideoRiskResult:
    return VideoRiskResult(
        score=0.52,
        decision="consider",
        reason_codes=["deepfake_frames"],
        weights={"deepfake": 0.35, "identity": 0.25, "replay": 0.2, "camera": 0.2},
        evidence=[
            RiskSignalEvidence(
                signal="deepfake",
                score=0.8,
                weight=0.35,
                contribution=0.28,
                threshold=0.68,
                triggered=True,
                reason_code="deepfake_frames",
                method="test",
                evidence={"suspicious_frame_count": 2},
            )
        ],
        deepfake=DeepfakeAnalysisResult(
            score=0.8,
            mean_score=0.7,
            max_score=0.9,
            suspicious_frame_count=2,
            suspicious_frames=[0, 5],
            method="test",
        ),
        temporal_identity=TemporalIdentityConsistencyResult(
            score=0.2,
            mean_drift=0.04,
            max_drift=0.08,
            suspicious_pair_count=0,
            embedding_frames=3,
            method="test",
        ),
        replay_attack=ReplayAttackResult(
            score=0.1,
            moire_score=0.0,
            flicker_score=0.0,
            duplication_score=0.1,
        ),
        camera_injection=CameraInjectionResult(
            score=0.05,
            metadata_score=0.0,
            challenge_timing_score=0.0,
            duplication_score=0.05,
        ),
    )
