"""Face biometric pipeline for selfie/video eKYC checks."""

from __future__ import annotations

import math
import os
import random
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal, cast

import cv2
import numpy as np

from ekyc_document.config import PipelineConfig
from ekyc_document.face_matching.arcface import ArcFaceMatcher
from ekyc_document.face_matching.embedder import InsightFaceEmbedder
from ekyc_document.face_matching.insightface_loader import create_face_analysis
from ekyc_document.liveness.frame_selection import ClientFrameMetric, select_best_frame_face
from ekyc_document.liveness.minifasnet import MiniFASNetAntiSpoof
from ekyc_document.lipsync_client import (
    LipSyncServiceError,
    probe_lipsync_service,
    request_lipsync_analysis,
)
from ekyc_document.onnx_models import OnnxModelRegistry
from ekyc_document.schemas import (
    ActiveLivenessChallengeResult,
    CameraInjectionResult,
    DecisionReason,
    DecisionType,
    DeepfakeAnalysisResult,
    FaceDetectionDetail,
    FaceMatchingResult,
    FaceQualityDetail,
    FrameDeepfakeScore,
    LivenessChallenge,
    LipSyncAnalysisResult,
    PassiveLivenessResult,
    ReplayAttackResult,
    RiskSignalEvidence,
    RiskTopReason,
    SelfieUploadResult,
    TemporalIdentityConsistencyResult,
    VideoRiskResult,
    VideoUploadResult,
    VoiceChallengeResult,
)
from ekyc_document.speech import SpeechVerifier


@dataclass
class BiometricFace:
    bbox: list[int]
    confidence: float
    face_count: int
    embedding: np.ndarray | None
    crop: np.ndarray
    landmarks: np.ndarray | None = None
    yaw: float = 0.0
    pitch: float = 0.0
    roll: float = 0.0
    aligned_crop: np.ndarray | None = None
    embedding_model: str | None = None

    @property
    def embedding_ready(self) -> bool:
        return self.embedding is not None and self.embedding.size > 0


@dataclass
class FrameFace:
    frame_index: int
    face: BiometricFace
    quality_score: float
    quality: FaceQualityDetail


@dataclass
class FrameSample:
    frame_index: int
    timestamp_ms: float | None
    frame: np.ndarray
    face: FrameFace | None = None


@dataclass
class VideoFrameExtraction:
    samples: list[FrameSample]
    fps: float | None
    frame_count: int | None
    duration_ms: float | None

    @property
    def frame_faces(self) -> list[FrameFace]:
        return [sample.face for sample in self.samples if sample.face is not None]


class BiometricPipeline:
    """Detect, assess, match and liveness-check portrait faces."""

    def __init__(self, config: PipelineConfig | None = None) -> None:
        self.config = config or PipelineConfig()
        self._app = None
        self._face_embedder: InsightFaceEmbedder | None = None
        self._liveness_model: MiniFASNetAntiSpoof | None = None
        self._speech_verifier: SpeechVerifier | None = None
        self._deepfake_session = None
        self._deepfake_hf_model = None
        self._deepfake_hf_processor = None
        self._deepfake_hf_unavailable_reason: str | None = None
        self._onnx_registry: OnnxModelRegistry | None = None

    def analyze_selfie(
        self,
        selfie_bytes: bytes,
        doc_face_bytes: bytes,
    ) -> SelfieUploadResult:
        selfie = _decode_image(selfie_bytes)
        doc_face = _decode_image(doc_face_bytes)

        warnings: list[str] = []
        selfie_face = self.detect_best_face(selfie)
        doc_face_result = self.detect_best_face(doc_face)

        if selfie_face is None:
            detail = FaceDetectionDetail(detected=False)
            quality = _empty_quality()
            passive = PassiveLivenessResult(
                score=0.0,
                passed=False,
                method="not_run",
                warnings=["Không phát hiện khuôn mặt trong ảnh selfie."],
            )
            return SelfieUploadResult(
                success=False,
                decision="failed",
                selfie_face=detail,
                quality_score=0.0,
                quality_details=quality,
                passive_liveness=passive,
                warnings=["Ảnh selfie phải có đầy đủ một khuôn mặt chân dung."],
            )

        quality_score, quality, quality_warnings = self.assess_face_quality(selfie, selfie_face)
        warnings.extend(quality_warnings)
        portrait_ok, portrait_warnings = self._validate_portrait(selfie, selfie_face)
        warnings.extend(portrait_warnings)

        passive = self.passive_liveness(selfie, selfie_face, quality_score=quality_score)
        warnings.extend(passive.warnings)

        matching = self.match_faces(doc_face_result, selfie_face)
        decision = self.decide(
            matching=matching,
            quality_score=quality_score,
            passive_liveness=passive,
            portrait_ok=portrait_ok,
            extra_blockers=[] if doc_face_result is not None else ["Không phát hiện khuôn mặt trên ảnh giấy tờ."],
        )

        return SelfieUploadResult(
            success=decision == "match",
            decision=decision,
            selfie_face=_face_detail(selfie_face, portrait_ok=portrait_ok),
            quality_score=quality_score,
            quality_details=quality,
            passive_liveness=passive,
            matching=matching,
            warnings=warnings,
        )

    def analyze_video(
        self,
        video_bytes: bytes,
        doc_face_bytes: bytes,
        challenge: LivenessChallenge | None = None,
        expected_text: str | None = None,
        client_best_frame_index: int | None = None,
        client_best_frame_progress: float | None = None,
        client_frame_metrics: list[ClientFrameMetric] | None = None,
        client_passive_liveness_score: float | None = None,
        client_transcript: str | None = None,
    ) -> VideoUploadResult:
        total_started = time.perf_counter()
        doc_face_started = time.perf_counter()
        doc_face_result = self.detect_best_face(_decode_image(doc_face_bytes))
        timings_ms = {"doc_face_detect": _elapsed_ms(doc_face_started)}
        selected_challenge = challenge or self.default_challenge()
        warnings: list[str] = []
        voice_result = self._verify_voice_if_needed(
            video_bytes,
            expected_text,
            timings_ms,
            client_transcript=client_transcript,
        )
        if voice_result is not None:
            warnings.extend(voice_result.warnings)
        extraction_started = time.perf_counter()
        extraction = self._extract_video_samples(video_bytes)
        timings_ms["frame_extract"] = _elapsed_ms(extraction_started)
        frame_faces = extraction.frame_faces

        if not frame_faces:
            liveness_started = time.perf_counter()
            passive = PassiveLivenessResult(
                score=0.0,
                passed=False,
                method="not_run",
                warnings=["Không phát hiện khuôn mặt trong video."],
            )
            active_results = [
                ActiveLivenessChallengeResult(
                    challenge=selected_challenge,
                    passed=False,
                    confidence=0.0,
                )
            ]
            timings_ms["liveness"] = _elapsed_ms(liveness_started)
            risk_started = time.perf_counter()
            risk = self.assess_video_risk(
                extraction=extraction,
                frame_faces=[],
                active_results=active_results,
                voice=voice_result,
                video_bytes=video_bytes,
            )
            timings_ms["risk"] = _elapsed_ms(risk_started)
            timings_ms["total"] = _elapsed_ms(total_started)
            matching = FaceMatchingResult(
                similarity=None,
                decision="failed",
                thresholds={
                    "match": self.config.face_match_threshold,
                    "consider": self.config.face_consider_threshold,
                },
                reason="Không có khuôn mặt live để so khớp.",
            )
            decision = self.decide(
                matching=matching,
                quality_score=0.0,
                passive_liveness=passive,
                portrait_ok=False,
                active_passed=False,
                risk=risk,
                voice_decision=voice_result.decision if voice_result is not None else None,
                extra_blockers=_voice_blockers(voice_result),
            )
            decision_reasons = self.explain_video_decision(
                decision=decision,
                matching=matching,
                quality_score=0.0,
                passive_liveness=passive,
                portrait_ok=False,
                active_results=active_results,
                risk=risk,
                voice=voice_result,
                doc_face_detected=doc_face_result is not None,
                live_face_detected=False,
            )
            return VideoUploadResult(
                success=False,
                decision=decision,
                frames_analyzed=len(extraction.samples),
                face_frames=0,
                challenge=selected_challenge,
                quality_score=0.0,
                quality_details=None,
                passive_liveness=passive,
                active_liveness=active_results,
                matching=matching,
                voice_verification=voice_result,
                risk=risk,
                decision_reasons=decision_reasons,
                evidence_artifacts=_video_evidence_artifacts(
                    extraction=extraction,
                    frame_faces=[],
                    risk=risk,
                    selected_challenge=selected_challenge,
                ),
                timings_ms=timings_ms,
                warnings=[
                    "Video phải là chân dung, thấy rõ đầy đủ khuôn mặt trong khung hình.",
                    *_risk_warnings(risk),
                    *warnings,
                ],
            )

        best = select_best_frame_face(
            frame_faces,
            client_best_frame_index=client_best_frame_index,
            client_best_frame_progress=client_best_frame_progress,
            client_metrics=client_frame_metrics,
        )
        if client_best_frame_progress is not None:
            warnings.append(
                "Đã map best frame từ MediaPipe client theo vị trí timeline video."
            )
        elif client_best_frame_index is not None and best.frame_index != client_best_frame_index:
            warnings.append(
                "Client best frame index không khớp frame server — dùng frame gần nhất có mặt."
            )
        elif client_best_frame_index is not None:
            warnings.append("Đã dùng best frame do MediaPipe client chọn trước khi upload.")
        if client_passive_liveness_score is not None:
            warnings.append(
                f"Client MiniFASNet WASM score: {client_passive_liveness_score:.2f}."
            )

        portrait_ok, portrait_warnings = self._validate_portrait_frame_sequence(frame_faces)
        warnings.extend(portrait_warnings)

        frame_by_index = {sample.frame_index: sample.frame for sample in extraction.samples}
        best_frame = frame_by_index.get(best.frame_index, best.face.crop)

        liveness_started = time.perf_counter()
        passive = self.passive_liveness(
            best_frame,
            best.face,
            quality_score=best.quality_score,
            frame_faces=frame_faces,
        )
        warnings.extend(passive.warnings)

        active_results = self.resolve_active_liveness(frame_faces, selected_challenge)
        if not self.config.skip_active_liveness and not active_results[0].passed:
            warnings.append(f"Không đạt thử thách active liveness: {selected_challenge}.")
        timings_ms["liveness"] = _elapsed_ms(liveness_started)

        matching_started = time.perf_counter()
        matching = self.match_faces(doc_face_result, best.face)
        timings_ms["matching"] = _elapsed_ms(matching_started)
        risk_started = time.perf_counter()
        risk = self.assess_video_risk(
            extraction=extraction,
            frame_faces=frame_faces,
            active_results=active_results,
            voice=voice_result,
            passive_liveness=passive,
            client_passive_liveness_score=client_passive_liveness_score,
            video_bytes=video_bytes,
        )
        timings_ms["risk"] = _elapsed_ms(risk_started)
        warnings.extend(_risk_warnings(risk))
        decision = self.decide(
            matching=matching,
            quality_score=best.quality_score,
            passive_liveness=passive,
            portrait_ok=portrait_ok,
            active_passed=all(result.passed for result in active_results),
            risk=risk,
            voice_decision=voice_result.decision if voice_result is not None else None,
            extra_blockers=[] if doc_face_result is not None else ["Không phát hiện khuôn mặt trên ảnh giấy tờ."]
            + _voice_blockers(voice_result),
        )
        timings_ms["total"] = _elapsed_ms(total_started)
        decision_reasons = self.explain_video_decision(
            decision=decision,
            matching=matching,
            quality_score=best.quality_score,
            passive_liveness=passive,
            portrait_ok=portrait_ok,
            active_results=active_results,
            risk=risk,
            voice=voice_result,
            doc_face_detected=doc_face_result is not None,
            live_face_detected=True,
        )

        return VideoUploadResult(
            success=decision == "match",
            decision=decision,
            frames_analyzed=len(frame_faces),
            face_frames=len(frame_faces),
            challenge=selected_challenge,
            best_frame_index=best.frame_index,
            best_live_face=_face_detail(best.face, portrait_ok=portrait_ok),
            quality_score=best.quality_score,
            quality_details=best.quality,
            passive_liveness=passive,
            active_liveness=active_results,
            matching=matching,
            voice_verification=voice_result,
            risk=risk,
            decision_reasons=decision_reasons,
            evidence_artifacts=_video_evidence_artifacts(
                extraction=extraction,
                frame_faces=frame_faces,
                risk=risk,
                selected_challenge=selected_challenge,
                best=best,
            ),
            timings_ms=timings_ms,
            warnings=warnings,
        )

    @property
    def onnx_registry(self) -> OnnxModelRegistry:
        if self._onnx_registry is None:
            self._onnx_registry = OnnxModelRegistry(self.config)
        return self._onnx_registry

    @property
    def liveness_model(self) -> MiniFASNetAntiSpoof:
        if self._liveness_model is None:
            self._liveness_model = MiniFASNetAntiSpoof(
                self.config,
                registry=self.onnx_registry,
            )
        return self._liveness_model

    def _verify_voice_if_needed(
        self,
        video_bytes: bytes,
        expected_text: str | None,
        timings_ms: dict[str, float],
        *,
        client_transcript: str | None = None,
    ) -> VoiceChallengeResult | None:
        if expected_text is None or not expected_text.strip():
            return None
        speech_started = time.perf_counter()
        voice_result = self.speech_verifier.verify_video(
            video_bytes,
            expected_text.strip(),
            client_transcript=client_transcript,
        )
        timings_ms["speech"] = _elapsed_ms(speech_started)
        return voice_result

    @property
    def speech_verifier(self) -> SpeechVerifier:
        if self._speech_verifier is None:
            self._speech_verifier = SpeechVerifier(self.config)
        return self._speech_verifier

    def random_challenge(self) -> LivenessChallenge:
        choices = self.config.active_liveness_challenges or ["blink"]
        return random.choice(choices)  # nosec - not security-sensitive

    def default_challenge(self) -> LivenessChallenge:
        challenge = self.config.default_liveness_challenge
        allowed = {"turn_left", "turn_right", "look_up", "look_down", "blink"}
        if challenge not in allowed:
            return "blink"
        return cast(LivenessChallenge, challenge)

    def detect_best_face(self, image: np.ndarray) -> BiometricFace | None:
        if self.config.face_detector != "opencv":
            self._lazy_init_face_embedder()
            if self._face_embedder is not None:
                embedded = self._face_embedder.detect_best(image)
                if embedded is not None:
                    x, y, w, h = embedded.bbox
                    raw_crop = image[y : y + h, x : x + w]
                    if raw_crop.size == 0:
                        raw_crop = embedded.aligned_crop
                    yaw, pitch, roll = _estimate_pose(embedded.bbox, embedded.landmarks)
                    return BiometricFace(
                        bbox=embedded.bbox,
                        confidence=embedded.confidence,
                        face_count=embedded.face_count,
                        embedding=embedded.embedding,
                        crop=raw_crop,
                        aligned_crop=embedded.aligned_crop,
                        landmarks=embedded.landmarks,
                        yaw=yaw,
                        pitch=pitch,
                        roll=roll,
                        embedding_model=embedded.embedding_model,
                    )

        self._lazy_init_face_model()
        if self._app == "opencv":
            return self._detect_opencv(image)

        assert self._app is not None
        faces = self._app.get(image)
        if not faces:
            return None

        best = max(faces, key=lambda face: float(getattr(face, "det_score", 0.0)))
        landmarks_array = getattr(best, "kps", None)
        if landmarks_array is None or np.asarray(landmarks_array).shape[0] < 5:
            return None

        x1, y1, x2, y2 = [int(v) for v in best.bbox]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(image.shape[1], x2), min(image.shape[0], y2)
        crop = image[y1:y2, x1:x2]
        if crop.size == 0:
            return None

        embedding = getattr(best, "normed_embedding", None)
        if embedding is None:
            embedding = getattr(best, "embedding", None)
        embedding_array = _normalize_embedding(embedding)
        if embedding_array is None:
            return None

        landmarks = np.asarray(landmarks_array, dtype=np.float32)
        yaw, pitch, roll = _estimate_pose([x1, y1, x2 - x1, y2 - y1], landmarks)

        return BiometricFace(
            bbox=[x1, y1, x2 - x1, y2 - y1],
            confidence=round(float(getattr(best, "det_score", 0.0)), 4),
            face_count=len(faces),
            embedding=embedding_array,
            crop=crop,
            landmarks=landmarks,
            yaw=yaw,
            pitch=pitch,
            roll=roll,
            embedding_model=f"insightface/{self.config.insightface_model}",
        )

    def assess_face_quality(
        self,
        image: np.ndarray,
        face: BiometricFace,
    ) -> tuple[float, FaceQualityDetail, list[str]]:
        gray = cv2.cvtColor(face.crop, cv2.COLOR_BGR2GRAY)
        blur_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        blur = _clip01((blur_var - 35.0) / 265.0)

        mean = float(np.mean(gray))
        if 85.0 <= mean <= 180.0:
            illumination = 1.0
        elif mean < 85.0:
            illumination = _clip01(mean / 85.0)
        else:
            illumination = _clip01((255.0 - mean) / 75.0)

        pose = _clip01(
            1.0
            - (
                abs(face.yaw) / 35.0
                + abs(face.pitch) / 30.0
                + abs(face.roll) / 25.0
            )
            / 3.0
        )
        coverage = _face_coverage(image, face.bbox)
        centered = _center_score(image, face.bbox)

        details = FaceQualityDetail(
            blur=round(blur, 4),
            pose=round(pose, 4),
            illumination=round(illumination, 4),
            face_coverage=round(coverage, 4),
            centered=round(centered, 4),
        )
        score = round(
            blur * 0.25
            + pose * 0.25
            + illumination * 0.20
            + coverage * 0.15
            + centered * 0.15,
            4,
        )

        warnings: list[str] = []
        if blur < 0.45:
            warnings.append("Khuôn mặt bị mờ, cần chụp/quay rõ nét hơn.")
        if pose < 0.45:
            warnings.append("Mặt lệch góc quá nhiều, cần nhìn thẳng hoặc làm đúng thử thách.")
        if illumination < 0.45:
            warnings.append("Ánh sáng trên khuôn mặt không đạt, cần đủ sáng và không ngược sáng.")
        if coverage < 0.45:
            warnings.append("Khuôn mặt quá nhỏ hoặc quá lớn trong khung hình.")
        if centered < 0.45:
            warnings.append("Khuôn mặt chưa nằm gần trung tâm khung hình.")
        if score < self.config.min_face_quality_score:
            warnings.append(
                f"Điểm chất lượng khuôn mặt ({score:.2f}) dưới ngưỡng {self.config.min_face_quality_score:.2f}."
            )
        return score, details, warnings

    def passive_liveness(
        self,
        image: np.ndarray,
        face: BiometricFace,
        *,
        quality_score: float,
        frame_faces: list[FrameFace] | None = None,
    ) -> PassiveLivenessResult:
        model_result = self.liveness_model.score(image, face.bbox)
        if model_result is not None:
            return PassiveLivenessResult(
                score=model_result.score,
                passed=model_result.passed,
                method=model_result.method,
            )

        if not self.config.allow_heuristic_fallback:
            return PassiveLivenessResult(
                score=0.0,
                passed=False,
                method="minifasnet_missing",
                warnings=["Thiếu minifasnet.onnx và heuristic fallback đang tắt."],
            )

        warnings = [
            "Chưa cấu hình EKYC_MINIFASNET_ONNX_PATH, đang dùng passive liveness heuristic."
        ]
        texture_score = _texture_liveness_score(face.crop)
        motion_score = _motion_liveness_score(frame_faces) if frame_faces else 0.5
        score = round(_clip01(quality_score * 0.45 + texture_score * 0.35 + motion_score * 0.20), 4)
        return PassiveLivenessResult(
            score=score,
            passed=score >= self.config.min_liveness_score,
            method="heuristic_fallback",
            warnings=warnings,
        )

    def match_faces(
        self,
        doc_face: BiometricFace | None,
        live_face: BiometricFace | None,
    ) -> FaceMatchingResult:
        return ArcFaceMatcher(self.config).compare(doc_face, live_face)

    def decide(
        self,
        *,
        matching: FaceMatchingResult,
        quality_score: float,
        passive_liveness: PassiveLivenessResult,
        portrait_ok: bool,
        active_passed: bool = True,
        risk: VideoRiskResult | None = None,
        voice_decision: DecisionType | None = None,
        extra_blockers: Iterable[str] = (),
    ) -> DecisionType:
        if any(extra_blockers) or not portrait_ok or not active_passed:
            return "failed"
        if voice_decision == "failed":
            return "failed"
        if risk is not None and risk.score >= self.config.video_risk_block_threshold:
            return "failed"
        if quality_score < self.config.min_face_quality_score:
            return "consider"
        if risk is not None and risk.score >= self.config.video_risk_review_threshold:
            if _risk_should_force_review(risk, passive_liveness, self.config):
                return "consider"
        if voice_decision == "consider":
            return "consider"
        if passive_liveness.score < self.config.min_manual_liveness_score:
            return "failed"
        if not passive_liveness.passed:
            return "consider"
        return matching.decision

    def explain_video_decision(
        self,
        *,
        decision: DecisionType,
        matching: FaceMatchingResult,
        quality_score: float,
        passive_liveness: PassiveLivenessResult,
        portrait_ok: bool,
        active_results: list[ActiveLivenessChallengeResult],
        risk: VideoRiskResult | None,
        voice: VoiceChallengeResult | None,
        doc_face_detected: bool,
        live_face_detected: bool,
    ) -> list[DecisionReason]:
        reasons: list[DecisionReason] = []
        _append_decision_reason(
            reasons,
            code="all_checks_passed",
            message="Tất cả kiểm tra chính đều đạt.",
            severity="info",
        )

        if not doc_face_detected:
            _append_decision_reason(
                reasons,
                code="document_face_missing",
                message="Không phát hiện khuôn mặt trên giấy tờ để đối chiếu.",
                severity="block",
            )
        if not live_face_detected:
            _append_decision_reason(
                reasons,
                code="live_face_missing",
                message="Không phát hiện khuôn mặt live trong video.",
                severity="block",
            )
        if not portrait_ok:
            _append_decision_reason(
                reasons,
                code="portrait_invalid",
                message="Khuôn mặt live không đạt điều kiện chân dung trong khung hình.",
                severity="block",
            )
        for item in active_results:
            if not item.passed:
                _append_decision_reason(
                    reasons,
                    code="active_liveness_failed",
                    message=f"Không đạt thử thách active liveness: {item.challenge}.",
                    severity="block",
                )
                break
        if voice is not None and voice.decision == "failed":
            _append_decision_reason(
                reasons,
                code="voice_mismatch",
                message="Giọng nói không khớp câu challenge.",
                severity="block",
            )
        if passive_liveness.score < self.config.min_manual_liveness_score:
            _append_decision_reason(
                reasons,
                code="passive_liveness_failed",
                message="Điểm passive liveness dưới ngưỡng chặn.",
                severity="block",
            )
        elif not passive_liveness.passed:
            _append_decision_reason(
                reasons,
                code="passive_liveness_review",
                message="Passive liveness chưa đạt ngưỡng tự động pass.",
                severity="warning",
            )
        if quality_score < self.config.min_face_quality_score:
            _append_decision_reason(
                reasons,
                code="face_quality_low",
                message="Chất lượng khuôn mặt live thấp, nên yêu cầu chụp/quay lại hoặc review.",
                severity="warning",
            )
        if risk is not None:
            if risk.score >= self.config.video_risk_block_threshold:
                _append_decision_reason(
                    reasons,
                    code="video_risk_block",
                    message="Risk engine vượt ngưỡng chặn.",
                    severity="block",
                )
            elif risk.score >= self.config.video_risk_review_threshold:
                _append_decision_reason(
                    reasons,
                    code="video_risk_review",
                    message="Risk engine vượt ngưỡng cần review.",
                    severity="warning",
                )
            for code in risk.reason_codes:
                _append_decision_reason(
                    reasons,
                    code=code,
                    message=_risk_reason_message(code),
                    severity="warning",
                )
        if voice is not None and voice.decision == "consider":
            _append_decision_reason(
                reasons,
                code="voice_review",
                message="Giọng nói nằm trong vùng cần review.",
                severity="warning",
            )
        if matching.decision == "failed":
            _append_decision_reason(
                reasons,
                code="face_mismatch",
                message="Khuôn mặt live không khớp khuôn mặt giấy tờ.",
                severity="block",
            )
        elif matching.decision == "consider":
            _append_decision_reason(
                reasons,
                code="face_match_review",
                message="Độ tương đồng khuôn mặt nằm trong vùng cần review.",
                severity="warning",
            )

        actionable = [reason for reason in reasons if reason.severity != "info"]
        return actionable or [reason for reason in reasons if reason.severity == "info"]

    def assess_video_risk(
        self,
        *,
        extraction: VideoFrameExtraction,
        frame_faces: list[FrameFace],
        active_results: list[ActiveLivenessChallengeResult],
        voice: VoiceChallengeResult | None = None,
        passive_liveness: PassiveLivenessResult | None = None,
        client_passive_liveness_score: float | None = None,
        video_bytes: bytes | None = None,
    ) -> VideoRiskResult:
        deepfake = self.analyze_deepfake_frames(frame_faces)
        lipsync = (
            self.analyze_lipsync_video(video_bytes)
            if video_bytes
            else _skipped_lipsync_result(method="lipsync_no_video")
        )
        identity = self.temporal_identity_consistency(frame_faces)
        replay = self.replay_attack_heuristics(extraction.samples)
        camera = self.camera_injection_heuristics(
            extraction=extraction,
            active_results=active_results,
            replay=replay,
        )

        replay_score = replay.score
        camera_score = camera.score
        if _passive_liveness_trusts_risk(passive_liveness, self.config):
            damp = self.config.risk_liveness_trust_dampening
            replay_score = round(_clip01(replay_score * damp), 4)
            camera_score = round(_clip01(camera_score * damp), 4)
        elif (
            client_passive_liveness_score is not None
            and client_passive_liveness_score >= self.config.min_liveness_score
        ):
            damp = self.config.risk_liveness_trust_dampening
            replay_score = round(_clip01(replay_score * damp), 4)
            camera_score = round(_clip01(camera_score * damp), 4)

        weights = _normalized_weights(
            self.config.video_risk_weights,
            required=("deepfake", "identity", "replay", "camera")
            + (("lipsync",) if not lipsync.skipped else ())
            + (("voice",) if voice is not None else ()),
        )
        evidence = [
            _risk_signal_evidence(
                signal="deepfake",
                score=deepfake.score,
                weight=weights["deepfake"],
                threshold=self.config.deepfake_suspicious_threshold,
                reason_code="deepfake_frames",
                method=deepfake.method,
                triggered=_deepfake_risk_triggered(deepfake, self.config),
                evidence={
                    "mean_score": deepfake.mean_score,
                    "max_score": deepfake.max_score,
                    "suspicious_frame_count": deepfake.suspicious_frame_count,
                    "suspicious_frames": deepfake.suspicious_frames,
                },
            ),
        ]
        if not lipsync.skipped:
            evidence.append(
                _risk_signal_evidence(
                    signal="lipsync",
                    score=lipsync.score,
                    weight=weights["lipsync"],
                    threshold=self.config.lipsync_suspicious_threshold,
                    reason_code="lipsync_deepfake",
                    method=lipsync.method,
                    triggered=_lipsync_risk_triggered(lipsync, self.config),
                    evidence={
                        "verdict": lipsync.verdict,
                        "manipulation_probability": lipsync.manipulation_probability,
                        "authenticity_confidence": lipsync.authenticity_confidence,
                        "is_fake": lipsync.is_fake,
                        "detail": lipsync.detail,
                    },
                )
            )
        evidence.extend(
            [
            _risk_signal_evidence(
                signal="identity",
                score=identity.score,
                weight=weights["identity"],
                threshold=self.config.video_risk_review_threshold,
                reason_code="temporal_identity_drift",
                method=identity.method,
                evidence={
                    "mean_drift": identity.mean_drift,
                    "max_drift": identity.max_drift,
                    "suspicious_pair_count": identity.suspicious_pair_count,
                    "embedding_frames": identity.embedding_frames,
                },
            ),
            _risk_signal_evidence(
                signal="replay",
                score=replay_score,
                weight=weights["replay"],
                threshold=self.config.replay_suspicious_threshold,
                reason_code="replay_attack",
                triggered=replay.confirmed and replay_score >= self.config.replay_suspicious_threshold,
                evidence={
                    "moire_score": replay.moire_score,
                    "flicker_score": replay.flicker_score,
                    "duplication_score": replay.duplication_score,
                    "duplicate_pairs": replay.duplicate_pairs,
                    "confirmed": replay.confirmed,
                    "face_motion_score": replay.face_motion_score,
                },
            ),
            _risk_signal_evidence(
                signal="camera",
                score=camera_score,
                weight=weights["camera"],
                threshold=self.config.camera_injection_suspicious_threshold,
                reason_code="camera_injection",
                triggered=(
                    camera_score >= self.config.camera_injection_suspicious_threshold
                    and (replay.confirmed or camera.metadata_score >= 0.67)
                ),
                evidence={
                    "metadata_score": camera.metadata_score,
                    "challenge_timing_score": camera.challenge_timing_score,
                    "duplication_score": camera.duplication_score,
                },
            ),
            ]
        )
        if voice is not None:
            voice_score = _clip01(voice.wer)
            if not voice.audio_detected:
                voice_score = 1.0
            evidence.append(
                _risk_signal_evidence(
                    signal="voice",
                    score=voice_score,
                    weight=weights["voice"],
                    threshold=self.config.voice_mismatch_risk_threshold,
                    reason_code="voice_mismatch",
                    method=voice.method,
                    evidence={
                        "wer": voice.wer,
                        "similarity": voice.similarity,
                        "passed": voice.passed,
                        "audio_detected": voice.audio_detected,
                    },
                )
            )
        score = round(_clip01(sum(item.contribution for item in evidence)), 4)
        reason_codes: list[str] = []
        for item in evidence:
            if item.triggered:
                reason_codes.append(item.reason_code)

        if score >= self.config.video_risk_block_threshold:
            decision: DecisionType = "failed"
        elif score >= self.config.video_risk_review_threshold:
            decision = "consider"
        else:
            decision = "match"
        replay_for_result = replay.model_copy(update={"score": replay_score})
        camera_for_result = camera.model_copy(update={"score": camera_score})
        return VideoRiskResult(
            score=score,
            decision=decision,
            reason_codes=reason_codes,
            weights=weights,
            evidence=evidence,
            top_reasons=_top_risk_reasons(evidence),
            deepfake=deepfake,
            temporal_identity=identity,
            replay_attack=replay_for_result,
            camera_injection=camera_for_result,
            lipsync=lipsync if not lipsync.skipped else None,
        )

    def analyze_lipsync_video(self, video_bytes: bytes) -> LipSyncAnalysisResult:
        if not self.config.lipsync_enabled or not self.config.lipsync_service_url:
            return _skipped_lipsync_result(method="lipsync_disabled")
        try:
            response = request_lipsync_analysis(
                base_url=self.config.lipsync_service_url,
                video_bytes=video_bytes,
                timeout_seconds=self.config.lipsync_timeout_seconds,
            )
        except LipSyncServiceError as exc:
            return LipSyncAnalysisResult(
                score=0.0,
                manipulation_probability=0.0,
                authenticity_confidence=0.0,
                verdict="skipped",
                is_fake=False,
                passed=True,
                skipped=True,
                method="lipsync_unavailable",
                warnings=[str(exc)],
            )

        score = round(_clip01(response.manipulation_probability), 4)
        triggered = _lipsync_risk_triggered_from_response(response, self.config)
        return LipSyncAnalysisResult(
            score=score,
            manipulation_probability=round(_clip01(response.manipulation_probability), 4),
            authenticity_confidence=round(_clip01(response.confidence), 4),
            verdict=cast(Literal["real", "fake", "uncertain", "skipped"], response.verdict),
            is_fake=response.is_fake,
            passed=not triggered,
            skipped=False,
            method="syncnet_lipsync",
            detail=response.detail,
        )

    def analyze_deepfake_frames(self, frame_faces: list[FrameFace]) -> DeepfakeAnalysisResult:
        frame_scores: list[FrameDeepfakeScore] = []
        warnings: list[str] = []
        for item in frame_faces:
            model_result = self._run_deepfake_model(item.face.crop)
            if model_result is None:
                if not self.config.allow_heuristic_fallback:
                    frame_method = "deepfake_onnx_missing"
                    score = 0.55
                    warnings.append(
                        "Thiếu deepfake_detector.onnx; gán điểm rủi ro trung bình vì heuristic fallback đang tắt."
                    )
                else:
                    frame_method = "gend_style_heuristic_fallback"
                    score = _deepfake_artifact_score(item.face.crop, item.quality_score)
            elif isinstance(model_result, tuple):
                score, frame_method = model_result
            else:
                score, frame_method = float(model_result), "deepfakebench_onnx"
            frame_scores.append(
                FrameDeepfakeScore(
                    frame_index=item.frame_index,
                    score=score,
                    suspicious=score >= self.config.deepfake_suspicious_threshold,
                    method=frame_method,
                )
            )

        if not frame_scores:
            warnings.append("Không đủ frame khuôn mặt để chạy deepfake detector.")
            return DeepfakeAnalysisResult(
                score=0.0,
                mean_score=0.0,
                max_score=0.0,
                suspicious_frame_count=0,
                method="not_run",
                warnings=warnings,
            )
        methods = {item.method for item in frame_scores}
        if "gend_style_heuristic_fallback" in methods:
            warnings.append(self._deepfake_model_unavailable_warning())
        scores = [item.score for item in frame_scores]
        mean_score = float(np.mean(scores))
        max_score = float(np.max(scores))
        suspicious_frames = [item.frame_index for item in frame_scores if item.suspicious]
        if not _deepfake_risk_triggered(
            DeepfakeAnalysisResult(
                score=0.0,
                mean_score=mean_score,
                max_score=max_score,
                suspicious_frame_count=len(suspicious_frames),
                suspicious_frames=suspicious_frames,
                frames=frame_scores,
                method="+".join(sorted(methods)),
            ),
            self.config,
        ):
            suspicious_frames = []
        suspicious_count = len(suspicious_frames)
        ratio = suspicious_count / max(len(frame_scores), 1)
        aggregate = round(_clip01(mean_score * 0.55 + max_score * 0.30 + ratio * 0.15), 4)
        if suspicious_count == 0:
            aggregate = round(_clip01(aggregate * 0.40), 4)
        return DeepfakeAnalysisResult(
            score=aggregate,
            mean_score=round(mean_score, 4),
            max_score=round(max_score, 4),
            suspicious_frame_count=suspicious_count,
            suspicious_frames=suspicious_frames,
            frames=frame_scores,
            method="+".join(sorted(methods)),
            warnings=warnings,
        )

    def temporal_identity_consistency(
        self,
        frame_faces: list[FrameFace],
    ) -> TemporalIdentityConsistencyResult:
        embeddings = [item.face.embedding for item in frame_faces if item.face.embedding_ready]
        if len(embeddings) < 2:
            return TemporalIdentityConsistencyResult(
                score=0.0,
                mean_drift=None,
                max_drift=None,
                suspicious_pair_count=0,
                embedding_frames=len(embeddings),
                method="arcface_embedding_drift",
                warnings=["Không đủ ArcFace embedding giữa các frame để kiểm tra identity drift."],
            )

        drifts = [
            _embedding_drift(embeddings[index], embeddings[index + 1])
            for index in range(len(embeddings) - 1)
        ]
        mean_drift = float(np.mean(drifts))
        max_drift = float(np.max(drifts))
        suspicious_pairs = sum(1 for drift in drifts if drift >= self.config.identity_drift_threshold)
        score = round(
            _clip01(
                mean_drift / self.config.identity_drift_threshold * 0.45
                + max_drift / (self.config.identity_drift_threshold * 1.8) * 0.40
                + suspicious_pairs / max(len(drifts), 1) * 0.15
            ),
            4,
        )
        warnings = []
        if suspicious_pairs:
            warnings.append("Embedding ArcFace thay đổi bất thường giữa các frame.")
        return TemporalIdentityConsistencyResult(
            score=score,
            mean_drift=round(mean_drift, 4),
            max_drift=round(max_drift, 4),
            suspicious_pair_count=suspicious_pairs,
            embedding_frames=len(embeddings),
            method="arcface_embedding_drift",
            warnings=warnings,
        )

    def replay_attack_heuristics(self, samples: list[FrameSample]) -> ReplayAttackResult:
        if len(samples) < 2:
            return ReplayAttackResult(
                score=0.0,
                moire_score=0.0,
                flicker_score=0.0,
                duplication_score=0.0,
                confirmed=False,
                warnings=["Không đủ frame để kiểm tra replay attack."],
            )

        face_frames = [_replay_face_crop(sample) for sample in samples]
        face_frames = [frame for frame in face_frames if frame is not None]
        full_frames = [sample.frame for sample in samples]

        moire_scores = [_moire_score(frame) for frame in (face_frames or full_frames)]
        moire_score = round(float(np.mean(moire_scores)), 4)
        flicker_score = _flicker_score(face_frames or full_frames)
        face_motion_score = _face_motion_score(samples)
        hamming_max = max(1, self.config.replay_dup_hamming_max)

        duplication_score = 0.0
        duplicate_pairs = 0
        if len(face_frames) >= 2:
            duplication_score, duplicate_pairs = _duplication_score(
                face_frames,
                hamming_max=hamming_max,
                saturation_ratio=0.70,
            )
        if len(full_frames) >= 2:
            full_dup, full_pairs = _duplication_score(
                full_frames,
                hamming_max=hamming_max + 1,
                saturation_ratio=0.55,
            )
            if len(face_frames) < 2:
                duplication_score, duplicate_pairs = full_dup, full_pairs
            elif full_dup > duplication_score:
                duplication_score = round(max(duplication_score, full_dup * 0.75), 4)
                duplicate_pairs = max(duplicate_pairs, full_pairs)

        if face_motion_score >= self.config.replay_motion_dup_relief_min:
            duplication_score = round(duplication_score * 0.45, 4)

        raw_score = round(
            _clip01(moire_score * 0.22 + flicker_score * 0.13 + duplication_score * 0.65),
            4,
        )
        confirmed = _replay_attack_confirmed(
            moire_score=moire_score,
            flicker_score=flicker_score,
            duplication_score=duplication_score,
            frozen_dup_min=self.config.replay_frozen_dup_min,
            confirm_moire_min=self.config.replay_confirm_moire_min,
            confirm_dup_min=self.config.replay_confirm_dup_min,
        )
        score = raw_score if confirmed else round(raw_score * 0.35, 4)

        warnings: list[str] = []
        if confirmed:
            if moire_score >= self.config.replay_confirm_moire_min:
                warnings.append("Phát hiện pattern tần số cao nghi moiré khi quay lại màn hình.")
            if flicker_score >= 0.58:
                warnings.append("Độ nhấp nháy ánh sáng giữa các frame cao bất thường.")
            if duplication_score >= self.config.replay_confirm_dup_min:
                warnings.append("Nhiều frame gần như trùng lặp, nghi replay hoặc stream bị inject.")
        return ReplayAttackResult(
            score=score,
            moire_score=moire_score,
            flicker_score=flicker_score,
            duplication_score=duplication_score,
            duplicate_pairs=duplicate_pairs,
            confirmed=confirmed,
            face_motion_score=face_motion_score,
            warnings=warnings,
        )

    def camera_injection_heuristics(
        self,
        *,
        extraction: VideoFrameExtraction,
        active_results: list[ActiveLivenessChallengeResult],
        replay: ReplayAttackResult,
    ) -> CameraInjectionResult:
        metadata_flags = 0
        if not extraction.fps or extraction.fps <= 0.0:
            metadata_flags += 1
        if extraction.frame_count is None or extraction.frame_count <= 0:
            metadata_flags += 1
        if extraction.duration_ms is None or extraction.duration_ms < 800.0:
            metadata_flags += 1
        metadata_score = round(_clip01(metadata_flags / 3.0), 4)

        challenge_confidence = (
            float(np.mean([result.confidence for result in active_results]))
            if active_results
            else 0.0
        )
        challenge_failed = any(not result.passed for result in active_results)
        too_short = extraction.duration_ms is not None and extraction.duration_ms < 1200.0
        challenge_timing_score = round(
            _clip01((0.55 if challenge_failed else 0.0) + (0.35 if too_short else 0.0) + (0.25 if challenge_confidence < 0.25 else 0.0)),
            4,
        )
        duplication_score = replay.duplication_score
        score = round(
            _clip01(metadata_score * 0.30 + challenge_timing_score * 0.35 + duplication_score * 0.35),
            4,
        )
        warnings: list[str] = []
        if metadata_score >= 0.5:
            warnings.append("Metadata video thiếu hoặc bất thường so với camera capture thông thường.")
        if challenge_timing_score >= 0.6:
            warnings.append("Timing/phản hồi challenge không nhất quán với thao tác live camera.")
        if duplication_score >= 0.6:
            warnings.append("Frame duplication làm tăng rủi ro camera injection.")
        return CameraInjectionResult(
            score=score,
            metadata_score=metadata_score,
            challenge_timing_score=challenge_timing_score,
            duplication_score=duplication_score,
            warnings=warnings,
        )

    def resolve_active_liveness(
        self,
        frame_faces: list[FrameFace],
        challenge: LivenessChallenge,
    ) -> list[ActiveLivenessChallengeResult]:
        if self.config.skip_active_liveness:
            return [
                ActiveLivenessChallengeResult(
                    challenge=challenge,
                    passed=True,
                    confidence=1.0,
                )
            ]
        return [self.evaluate_active_challenge(frame_faces, challenge)]

    def evaluate_active_challenge(
        self,
        frame_faces: list[FrameFace],
        challenge: LivenessChallenge,
    ) -> ActiveLivenessChallengeResult:
        if not frame_faces:
            return ActiveLivenessChallengeResult(challenge=challenge, passed=False, confidence=0.0)

        yaws = [item.face.yaw for item in frame_faces]
        pitches = [item.face.pitch for item in frame_faces]
        if challenge == "turn_left":
            confidence = _clip01(abs(min(yaws)) / 18.0)
        elif challenge == "turn_right":
            confidence = _clip01(max(yaws) / 18.0)
        elif challenge == "look_up":
            confidence = _clip01(abs(min(pitches)) / 14.0)
        elif challenge == "look_down":
            confidence = _clip01(max(pitches) / 14.0)
        else:
            confidence = _blink_confidence(frame_faces)

        return ActiveLivenessChallengeResult(
            challenge=challenge,
            passed=confidence >= 0.65,
            confidence=round(confidence, 4),
        )

    def _extract_video_faces(self, video_bytes: bytes) -> list[FrameFace]:
        return self._extract_video_samples(video_bytes).frame_faces

    def _extract_video_samples(self, video_bytes: bytes) -> VideoFrameExtraction:
        suffix = ".mp4"
        handle = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        temp_path = Path(handle.name)
        try:
            handle.write(video_bytes)
            handle.close()
            cap = cv2.VideoCapture(str(temp_path))
            if not cap.isOpened():
                raise ValueError("Không đọc được video upload.")

            samples: list[FrameSample] = []
            frame_index = 0
            fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
            frame_count_raw = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            fps_value = fps if fps > 0.0 else None
            frame_count = frame_count_raw if frame_count_raw > 0 else None
            duration_ms = (
                frame_count / fps_value * 1000.0
                if frame_count is not None and fps_value is not None
                else None
            )
            stride = _adaptive_video_stride(
                configured_stride=max(1, self.config.video_frame_stride),
                frame_count=frame_count,
                max_samples=max(1, self.config.max_video_frames),
                target_samples=max(1, self.config.target_video_samples),
                enabled=self.config.adaptive_video_sampling,
            )
            while len(samples) < self.config.max_video_frames:
                ok, frame = cap.read()
                if not ok:
                    break
                if frame_index % stride == 0:
                    timestamp_ms = cap.get(cv2.CAP_PROP_POS_MSEC)
                    face_frame = None
                    face = self.detect_best_face(frame)
                    if face is not None:
                        quality_score, quality, _ = self.assess_face_quality(frame, face)
                        face_frame = FrameFace(
                            frame_index=frame_index,
                            face=face,
                            quality_score=quality_score,
                            quality=quality,
                        )
                    samples.append(
                        FrameSample(
                            frame_index=frame_index,
                            timestamp_ms=float(timestamp_ms) if timestamp_ms >= 0.0 else None,
                            frame=frame,
                            face=face_frame,
                        )
                    )
                frame_index += 1
            cap.release()
            return VideoFrameExtraction(
                samples=samples,
                fps=fps_value,
                frame_count=frame_count,
                duration_ms=duration_ms,
            )
        finally:
            try:
                os.unlink(temp_path)
            except OSError:
                pass

    def _validate_portrait(self, image: np.ndarray, face: BiometricFace) -> tuple[bool, list[str]]:
        warnings: list[str] = []
        coverage_ratio = _bbox_area(face.bbox) / float(image.shape[0] * image.shape[1])
        if face.face_count != 1:
            warnings.append("Ảnh/video chỉ được có đúng một khuôn mặt.")
        if coverage_ratio < self.config.min_face_coverage:
            warnings.append("Khuôn mặt quá nhỏ; cần chụp chân dung gần hơn.")
        if coverage_ratio > self.config.max_face_coverage:
            warnings.append("Khuôn mặt quá sát camera; cần thấy đầy đủ chân dung.")
        if _center_score(image, face.bbox) < 0.45:
            warnings.append("Khuôn mặt phải nằm gần trung tâm khung hình.")
        return not warnings, warnings

    def _validate_portrait_frame_sequence(
        self,
        frame_faces: list[FrameFace],
    ) -> tuple[bool, list[str]]:
        warnings: list[str] = []
        if len(frame_faces) < self.config.min_video_face_frames:
            warnings.append(
                f"Video cần tối thiểu {self.config.min_video_face_frames} frame có khuôn mặt rõ."
            )
        multi_face_frames = sum(1 for item in frame_faces if item.face.face_count != 1)
        if multi_face_frames:
            warnings.append("Video chỉ được có một khuôn mặt trong khung hình.")
        small_or_large = [
            item
            for item in frame_faces
            if item.quality.face_coverage < 0.45
        ]
        if len(small_or_large) > max(1, len(frame_faces) // 3):
            warnings.append("Video cần thấy đầy đủ khuôn mặt chân dung trong phần lớn thời lượng.")
        return not warnings, warnings

    def _lazy_init_face_embedder(self) -> None:
        if self._face_embedder is None and self.config.face_detector != "opencv":
            self._face_embedder = InsightFaceEmbedder(self.config)

    def _lazy_init_face_model(self) -> None:
        self._lazy_init_face_embedder()
        if self._app is not None:
            return
        self._app = create_face_analysis(self.config)

    def _detect_opencv(self, image: np.ndarray) -> BiometricFace | None:
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        detector = cv2.CascadeClassifier(cascade_path)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        faces = detector.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))
        if len(faces) == 0:
            return None
        x, y, w, h = max(faces, key=lambda item: item[2] * item[3])
        crop = image[y : y + h, x : x + w]
        return BiometricFace(
            bbox=[int(x), int(y), int(w), int(h)],
            confidence=0.6,
            face_count=len(faces),
            embedding=None,
            crop=crop,
            embedding_model="opencv/haar_no_embedding",
        )

    def _run_minifasnet(self, image: np.ndarray, bbox: list[int]) -> tuple[float, str] | None:
        if self.config.prefer_onnx:
            return self.onnx_registry.run_minifasnet(image, bbox)
        return None

    def _run_deepfake_model(self, face_crop: np.ndarray) -> tuple[float, str] | None:
        if self.config.prefer_onnx:
            onnx_result = self.onnx_registry.run_deepfake(face_crop)
            if onnx_result is not None:
                return onnx_result
        if not self.config.prefer_onnx or self.config.deepfake_hf_model:
            return self._run_hf_deepfake_model(face_crop)
        return None

    def _run_hf_deepfake_model(self, face_crop: np.ndarray) -> tuple[float, str] | None:
        model_name = self.config.deepfake_hf_model
        if not model_name or self._deepfake_hf_unavailable_reason is not None:
            return None
        try:
            if self._deepfake_hf_model is None or self._deepfake_hf_processor is None:
                from transformers import AutoImageProcessor, AutoModelForImageClassification

                self._deepfake_hf_model = AutoModelForImageClassification.from_pretrained(model_name)
                self._deepfake_hf_processor = AutoImageProcessor.from_pretrained(model_name)
                self._deepfake_hf_model.eval()

            import torch
            from PIL import Image

            rgb = cv2.cvtColor(face_crop, cv2.COLOR_BGR2RGB)
            image = Image.fromarray(rgb).convert("RGB")
            inputs = self._deepfake_hf_processor(images=image, return_tensors="pt")
            with torch.no_grad():
                outputs = self._deepfake_hf_model(**inputs)
                probs = torch.nn.functional.softmax(outputs.logits, dim=1).squeeze().tolist()
            if not isinstance(probs, list):
                fake_score = float(probs)
            else:
                labels = getattr(self._deepfake_hf_model.config, "id2label", {}) or {}
                fake_index = _fake_label_index(labels, len(probs))
                fake_score = float(probs[fake_index])
            return round(_clip01(fake_score), 4), f"huggingface/{model_name}"
        except Exception as exc:  # pragma: no cover - depends on optional local model deps/network
            api_result = self._run_hf_inference_api(face_crop, model_name)
            if api_result is not None:
                return api_result
            self._deepfake_hf_unavailable_reason = str(exc)
            return None

    def _run_hf_inference_api(self, face_crop: np.ndarray, model_name: str) -> tuple[float, str] | None:
        token = os.getenv("HF_TOKEN")
        if not token:
            return None
        try:
            from io import BytesIO

            from huggingface_hub import InferenceClient
            from PIL import Image

            rgb = cv2.cvtColor(face_crop, cv2.COLOR_BGR2RGB)
            image = Image.fromarray(rgb).convert("RGB")
            buffer = BytesIO()
            image.save(buffer, format="JPEG")
            client = InferenceClient(provider="hf-inference", api_key=token)
            output = client.image_classification(buffer.getvalue(), model=model_name)
            scores = {
                str(item.get("label", "")).lower(): float(item.get("score", 0.0))
                for item in output
                if isinstance(item, dict)
            }
            fake_score = next(
                (score for label, score in scores.items() if "fake" in label),
                None,
            )
            if fake_score is None:
                return None
            return round(_clip01(fake_score), 4), f"huggingface_api/{model_name}"
        except Exception:
            return None

    def _deepfake_model_unavailable_warning(self) -> str:
        model_path = self.config.deepfake_onnx_path
        if self.config.deepfake_hf_model:
            if self._deepfake_hf_unavailable_reason:
                return (
                    f"Không tải được HuggingFace deepfake model {self.config.deepfake_hf_model}: "
                    f"{self._deepfake_hf_unavailable_reason}; đang dùng heuristic GenD-style cho artifact theo frame."
                )
            return (
                f"Chưa chạy được HuggingFace deepfake model {self.config.deepfake_hf_model}; "
                "đang dùng heuristic GenD-style cho artifact theo frame."
            )
        if os.getenv("EKYC_DEEPFAKE_ONNX_PATH") and model_path is not None:
            return (
                "Không tìm thấy file model tại EKYC_DEEPFAKE_ONNX_PATH="
                f"{model_path}; đang dùng heuristic GenD-style cho artifact theo frame."
            )
        return (
            "Chưa cấu hình EKYC_DEEPFAKE_ONNX_PATH, đang dùng heuristic GenD-style "
            "cho artifact theo frame."
        )

    def diagnostics(self) -> dict[str, object]:
        return {
            "face_detector": self.config.face_detector,
            "insightface_model": self.config.insightface_model,
            "arcface": ArcFaceMatcher(self.config).diagnostics(),
            "face_embedder": self._face_embedder.diagnostics()
            if self._face_embedder is not None
            else InsightFaceEmbedder(self.config).diagnostics(),
            "use_gpu": self.config.use_gpu,
            "video_sampling": {
                "adaptive": self.config.adaptive_video_sampling,
                "configured_stride": self.config.video_frame_stride,
                "target_samples": self.config.target_video_samples,
                "max_frames": self.config.max_video_frames,
            },
            "active_liveness": {
                "skip": self.config.skip_active_liveness,
                "default_challenge": self.config.default_liveness_challenge,
                "challenges": self.config.active_liveness_challenges,
            },
            "onnx": self.onnx_registry.diagnostics(),
            "risk": {
                "weights": _normalized_weights(
                    self.config.video_risk_weights,
                    required=("deepfake", "lipsync", "identity", "replay", "camera", "voice"),
                ),
                "review_threshold": self.config.video_risk_review_threshold,
                "block_threshold": self.config.video_risk_block_threshold,
            },
            "lipsync": {
                "enabled": self.config.lipsync_enabled,
                "service_url": self.config.lipsync_service_url,
                "suspicious_threshold": self.config.lipsync_suspicious_threshold,
                "probe": probe_lipsync_service(base_url=self.config.lipsync_service_url)
                if self.config.lipsync_service_url
                else {"reachable": False, "error": "EKYC_LIPSYNC_SERVICE_URL not set"},
            },
            "speech": self.speech_verifier.diagnostics(),
        }


def _decode_image(content: bytes) -> np.ndarray:
    if not content:
        raise ValueError("File ảnh rỗng.")
    arr = np.frombuffer(content, dtype=np.uint8)
    image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Không đọc được file ảnh.")
    return image


def _face_detail(face: BiometricFace, *, portrait_ok: bool) -> FaceDetectionDetail:
    return FaceDetectionDetail(
        detected=True,
        face_count=face.face_count,
        bbox=face.bbox,
        confidence=face.confidence,
        embedding_model=face.embedding_model,
        embedding_ready=face.embedding_ready,
        portrait_ok=portrait_ok,
    )


def _empty_quality() -> FaceQualityDetail:
    return FaceQualityDetail(
        blur=0.0,
        pose=0.0,
        illumination=0.0,
        face_coverage=0.0,
        centered=0.0,
    )


def _normalize_embedding(raw: object) -> np.ndarray | None:
    if raw is None:
        return None
    embedding = np.asarray(raw, dtype=np.float32).reshape(-1)
    norm = float(np.linalg.norm(embedding))
    if norm <= 0.0:
        return None
    return embedding / norm


def _estimate_pose(
    bbox: list[int],
    landmarks: np.ndarray | None,
) -> tuple[float, float, float]:
    if landmarks is None or landmarks.shape[0] < 5:
        return 0.0, 0.0, 0.0

    left_eye, right_eye, nose, mouth_left, mouth_right = landmarks[:5]
    eye_mid = (left_eye + right_eye) / 2.0
    mouth_mid = (mouth_left + mouth_right) / 2.0
    eye_dist = max(float(np.linalg.norm(right_eye - left_eye)), 1.0)

    yaw = float((nose[0] - eye_mid[0]) / eye_dist * 45.0)
    vertical_ratio = float((nose[1] - eye_mid[1]) / eye_dist)
    pitch = (vertical_ratio - 0.65) * 35.0
    roll = math.degrees(math.atan2(float(right_eye[1] - left_eye[1]), float(right_eye[0] - left_eye[0])))

    # Mouth landmarks stabilize pitch when available.
    face_height = max(float(bbox[3]), 1.0)
    mouth_ratio = float((mouth_mid[1] - nose[1]) / face_height)
    pitch += (0.22 - mouth_ratio) * 25.0
    return yaw, pitch, roll


def _clip01(value: float) -> float:
    return float(max(0.0, min(1.0, value)))


def _elapsed_ms(started_at: float) -> float:
    return round((time.perf_counter() - started_at) * 1000.0, 2)


def _normalized_weights(
    raw_weights: dict[str, float],
    *,
    required: tuple[str, ...],
) -> dict[str, float]:
    usable = {
        key: max(0.0, float(raw_weights.get(key, 0.0)))
        for key in required
    }
    total = sum(usable.values())
    if total <= 0.0:
        equal = round(1.0 / len(required), 4)
        return {key: equal for key in required}
    normalized = {key: round(value / total, 4) for key, value in usable.items()}
    drift = round(1.0 - sum(normalized.values()), 4)
    if drift and required:
        normalized[required[0]] = round(normalized[required[0]] + drift, 4)
    return normalized


def _risk_signal_evidence(
    *,
    signal: str,
    score: float,
    weight: float,
    threshold: float,
    reason_code: str,
    evidence: dict[str, object],
    method: str | None = None,
    triggered: bool | None = None,
) -> RiskSignalEvidence:
    clipped_score = round(_clip01(score), 4)
    clipped_weight = round(_clip01(weight), 4)
    is_triggered = clipped_score >= threshold if triggered is None else triggered
    return RiskSignalEvidence(
        signal=signal,
        score=clipped_score,
        weight=clipped_weight,
        contribution=round(_clip01(clipped_score * clipped_weight), 4),
        threshold=round(_clip01(threshold), 4),
        triggered=is_triggered,
        reason_code=reason_code,
        method=method,
        evidence=evidence,
    )


def _adaptive_video_stride(
    *,
    configured_stride: int,
    frame_count: int | None,
    max_samples: int,
    target_samples: int,
    enabled: bool,
) -> int:
    if not enabled or frame_count is None or frame_count <= 0:
        return configured_stride
    sample_budget = min(max_samples, target_samples)
    if sample_budget <= 0:
        return configured_stride
    adaptive_stride = max(1, math.ceil(frame_count / sample_budget))
    return max(configured_stride, adaptive_stride)


def _softmax(values: np.ndarray) -> np.ndarray:
    shifted = values - np.max(values)
    exp = np.exp(shifted)
    return exp / np.sum(exp)


def _video_evidence_artifacts(
    *,
    extraction: VideoFrameExtraction,
    frame_faces: list[FrameFace],
    risk: VideoRiskResult | None,
    selected_challenge: LivenessChallenge,
    best: FrameFace | None = None,
) -> dict[str, object]:
    return {
        "challenge": selected_challenge,
        "frames_sampled": len(extraction.samples),
        "sampled_frame_indices": [sample.frame_index for sample in extraction.samples[:30]],
        "face_frame_indices": [item.frame_index for item in frame_faces[:30]],
        "best_frame_index": best.frame_index if best is not None else None,
        "best_face_bbox": best.face.bbox if best is not None else None,
        "video_metadata": {
            "fps": extraction.fps,
            "frame_count": extraction.frame_count,
            "duration_ms": extraction.duration_ms,
        },
        "suspicious_frame_indices": (
            risk.deepfake.suspicious_frames[:30] if risk is not None else []
        ),
        "top_risk_reasons": (
            [reason.model_dump() for reason in risk.top_reasons] if risk is not None else []
        ),
    }


def _top_risk_reasons(
    evidence: list[RiskSignalEvidence],
    *,
    limit: int = 3,
) -> list[RiskTopReason]:
    if not evidence:
        return []

    ranked = sorted(
        evidence,
        key=lambda item: (item.triggered, item.contribution, item.score),
        reverse=True,
    )
    top: list[RiskTopReason] = []
    for item in ranked:
        if not item.triggered and item.contribution < 0.08:
            continue
        top.append(
            RiskTopReason(
                signal=item.signal,
                reason_code=item.reason_code,
                score=item.score,
                contribution=item.contribution,
                triggered=item.triggered,
                message=_risk_reason_message(item.reason_code),
                evidence=item.evidence,
            )
        )
        if len(top) >= limit:
            break
    return top


def _append_decision_reason(
    reasons: list[DecisionReason],
    *,
    code: str,
    message: str,
    severity: str,
    source: str = "biometric",
) -> None:
    if any(reason.code == code for reason in reasons):
        return
    reasons.append(
        DecisionReason(
            code=code,
            message=message,
            severity=cast(Literal["info", "warning", "block"], severity),
            source=source,
        )
    )


def _risk_reason_message(code: str) -> str:
    messages = {
        "deepfake_frames": "Một số frame có điểm deepfake cao.",
        "lipsync_deepfake": "Phân tích lip-sync (SyncNet) phát hiện dấu hiệu video giả / môi không khớp audio.",
        "temporal_identity_drift": "Embedding khuôn mặt thay đổi bất thường giữa các frame.",
        "replay_attack": "Video có dấu hiệu quay lại màn hình hoặc lặp frame.",
        "camera_injection": "Metadata/timing video có dấu hiệu camera injection.",
        "voice_mismatch": "Giọng nói không khớp nội dung challenge.",
    }
    return messages.get(code, f"Tín hiệu rủi ro: {code}.")


def _voice_blockers(voice: VoiceChallengeResult | None) -> list[str]:
    if voice is None:
        return []
    if voice.decision == "failed":
        return ["Speech verification không đạt: nội dung giọng nói không khớp challenge."]
    return []


def _risk_warnings(risk: VideoRiskResult) -> list[str]:
    warnings: list[str] = []
    if risk.reason_codes:
        warnings.append(f"Risk engine phát hiện signal bất thường: {', '.join(risk.reason_codes)}.")
    warnings.extend(risk.deepfake.warnings)
    warnings.extend(risk.temporal_identity.warnings)
    warnings.extend(risk.replay_attack.warnings)
    warnings.extend(risk.camera_injection.warnings)
    if risk.lipsync is not None:
        warnings.extend(risk.lipsync.warnings)
    return warnings


def _embedding_drift(left: np.ndarray, right: np.ndarray) -> float:
    return round(_clip01(1.0 - float(np.dot(left, right))), 4)


def _fake_label_index(labels: dict[int | str, str], class_count: int) -> int:
    for raw_index, raw_label in labels.items():
        label = str(raw_label).lower()
        if "fake" not in label:
            continue
        try:
            index = int(raw_index)
        except (TypeError, ValueError):
            continue
        if 0 <= index < class_count:
            return index
    return 0


def _deepfake_artifact_score(face_crop: np.ndarray, quality_score: float) -> float:
    gray = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)
    lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    overly_smooth = _clip01((45.0 - lap_var) / 45.0)

    ycrcb = cv2.cvtColor(face_crop, cv2.COLOR_BGR2YCrCb)
    chroma_noise = float(np.std(ycrcb[:, :, 1]) + np.std(ycrcb[:, :, 2])) / 2.0
    chroma_artifact = _clip01((chroma_noise - 8.0) / 28.0)

    edges = cv2.Canny(gray, 80, 160)
    edge_density = float(np.mean(edges > 0))
    edge_artifact = _clip01((edge_density - 0.12) / 0.18)
    quality_penalty = _clip01((0.62 - quality_score) / 0.62)
    return round(
        _clip01(
            overly_smooth * 0.30
            + chroma_artifact * 0.25
            + edge_artifact * 0.20
            + quality_penalty * 0.25
        ),
        4,
    )


def _moire_score(frame: np.ndarray) -> float:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    small = cv2.resize(gray, (128, 128), interpolation=cv2.INTER_AREA).astype(np.float32)
    small -= float(np.mean(small))
    spectrum = np.abs(np.fft.fftshift(np.fft.fft2(small)))
    h, w = spectrum.shape
    cy, cx = h // 2, w // 2
    yy, xx = np.ogrid[:h, :w]
    radius = np.sqrt((yy - cy) ** 2 + (xx - cx) ** 2)
    total = float(np.sum(spectrum)) + 1e-6
    low_band = float(np.sum(spectrum[radius <= 20]) / total)
    mid_band = float(np.sum(spectrum[(radius > 28) & (radius <= 48)]) / total)
    high_freq_ratio = float(np.sum(spectrum[radius > 34]) / total)
    periodic_ratio = mid_band / max(low_band, 1e-6)
    row_energy = float(np.mean(np.abs(np.diff(small, axis=0))))
    col_energy = float(np.mean(np.abs(np.diff(small, axis=1))))
    grid_energy = _clip01(abs(row_energy - col_energy) / max(row_energy + col_energy, 1e-6) * 3.0)
    periodic_signal = _clip01(max(0.0, periodic_ratio - 1.15) / 2.2)
    compression_noise = _clip01(max(0.0, high_freq_ratio - 0.22) / 0.35)
    return round(_clip01(periodic_signal * 0.55 + grid_energy * 0.25 + compression_noise * 0.20), 4)


def _duplication_score(
    frames: list[np.ndarray],
    *,
    hamming_max: int = 2,
    saturation_ratio: float = 0.55,
) -> tuple[float, int]:
    hashes = [_difference_hash(frame) for frame in frames]
    duplicate_pairs = 0
    comparisons = 0
    for index in range(len(hashes) - 1):
        comparisons += 1
        if _hamming_distance(hashes[index], hashes[index + 1]) <= hamming_max:
            duplicate_pairs += 1
    if comparisons == 0:
        return 0.0, 0
    ratio = duplicate_pairs / comparisons
    return round(_clip01(ratio / saturation_ratio), 4), duplicate_pairs


def _replay_face_crop(sample: FrameSample) -> np.ndarray | None:
    if sample.face is None:
        return None
    crop = sample.face.face.crop
    if crop is not None and crop.size > 0:
        return crop
    x, y, w, h = sample.face.face.bbox
    frame = sample.frame
    x2, y2 = min(frame.shape[1], x + w), min(frame.shape[0], y + h)
    if x2 <= x or y2 <= y:
        return None
    return frame[y:y2, x:x2]


def _face_motion_score(samples: list[FrameSample]) -> float:
    crops: list[np.ndarray] = []
    for sample in samples:
        crop = _replay_face_crop(sample)
        if crop is not None and crop.size > 0:
            crops.append(crop)
    if len(crops) < 2:
        return 0.0
    diffs: list[float] = []
    for index in range(len(crops) - 1):
        left = cv2.cvtColor(crops[index], cv2.COLOR_BGR2GRAY).astype(np.float32)
        right = cv2.cvtColor(crops[index + 1], cv2.COLOR_BGR2GRAY).astype(np.float32)
        if left.shape != right.shape:
            right = cv2.resize(right, (left.shape[1], left.shape[0]))
        diffs.append(float(np.mean(np.abs(left - right))))
    return round(_clip01(float(np.mean(diffs)) / 7.5), 4)


def _replay_attack_confirmed(
    *,
    moire_score: float,
    flicker_score: float,
    duplication_score: float,
    frozen_dup_min: float,
    confirm_moire_min: float,
    confirm_dup_min: float,
) -> bool:
    if duplication_score >= frozen_dup_min:
        return True
    if moire_score >= confirm_moire_min and duplication_score >= confirm_dup_min:
        return True
    if moire_score >= 0.74 and flicker_score >= 0.58 and duplication_score >= confirm_dup_min * 0.85:
        return True
    return False


def _deepfake_risk_triggered(result: DeepfakeAnalysisResult, config: PipelineConfig) -> bool:
    if result.suspicious_frame_count >= config.deepfake_min_suspicious_frames:
        return True
    if result.max_score >= config.deepfake_single_frame_block_score:
        return True
    return False


def _skipped_lipsync_result(
    *,
    method: str,
    warnings: list[str] | None = None,
) -> LipSyncAnalysisResult:
    return LipSyncAnalysisResult(
        score=0.0,
        manipulation_probability=0.0,
        authenticity_confidence=0.0,
        verdict="skipped",
        is_fake=False,
        passed=True,
        skipped=True,
        method=method,
        warnings=warnings or [],
    )


def _lipsync_risk_triggered(result: LipSyncAnalysisResult, config: PipelineConfig) -> bool:
    if result.skipped:
        return False
    return (
        result.is_fake
        or result.verdict == "fake"
        or result.score >= config.lipsync_suspicious_threshold
    )


def _lipsync_risk_triggered_from_response(
    response: object,
    config: PipelineConfig,
) -> bool:
    is_fake = bool(getattr(response, "is_fake", False))
    verdict = str(getattr(response, "verdict", "uncertain"))
    manipulation_probability = float(getattr(response, "manipulation_probability", 0.0))
    return (
        is_fake
        or verdict == "fake"
        or manipulation_probability >= config.lipsync_suspicious_threshold
    )


def _passive_liveness_trusts_risk(
    passive: PassiveLivenessResult | None,
    config: PipelineConfig,
) -> bool:
    if passive is None:
        return False
    return passive.passed and passive.score >= config.risk_liveness_trust_threshold


def _risk_should_force_review(
    risk: VideoRiskResult,
    passive: PassiveLivenessResult,
    config: PipelineConfig,
) -> bool:
    if any(
        code in risk.reason_codes
        for code in ("deepfake_frames", "temporal_identity_drift", "voice_mismatch")
    ):
        return True
    if "replay_attack" in risk.reason_codes and risk.replay_attack.confirmed:
        return True
    if "camera_injection" in risk.reason_codes and risk.camera_injection.score >= 0.68:
        return True
    if not _passive_liveness_trusts_risk(passive, config):
        return True
    return False


def _flicker_score(frames: list[np.ndarray]) -> float:
    means = [
        float(np.mean(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)))
        for frame in frames
    ]
    if len(means) < 2:
        return 0.0
    deltas = np.abs(np.diff(np.asarray(means, dtype=np.float32)))
    mean_delta = float(np.mean(deltas))
    alternating = 0.0
    if len(deltas) >= 3:
        signs = np.sign(np.diff(np.asarray(means, dtype=np.float32)))
        alternating = float(np.mean(signs[1:] != signs[:-1]))
    return round(_clip01(mean_delta / 18.0 * 0.70 + alternating * 0.30), 4)


def _difference_hash(frame: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    resized = cv2.resize(gray, (9, 8), interpolation=cv2.INTER_AREA)
    return resized[:, 1:] > resized[:, :-1]


def _hamming_distance(left: np.ndarray, right: np.ndarray) -> int:
    return int(np.count_nonzero(left != right))


def _bbox_area(bbox: list[int]) -> int:
    return max(0, bbox[2]) * max(0, bbox[3])


def _face_coverage(image: np.ndarray, bbox: list[int]) -> float:
    ratio = _bbox_area(bbox) / float(image.shape[0] * image.shape[1])
    target = 0.22
    if ratio <= target:
        return _clip01(ratio / target)
    return _clip01(1.0 - ((ratio - target) / 0.45))


def _center_score(image: np.ndarray, bbox: list[int]) -> float:
    h, w = image.shape[:2]
    face_cx = bbox[0] + bbox[2] / 2.0
    face_cy = bbox[1] + bbox[3] / 2.0
    dx = abs(face_cx - w / 2.0) / (w / 2.0)
    dy = abs(face_cy - h / 2.0) / (h / 2.0)
    return _clip01(1.0 - (dx * 0.6 + dy * 0.4))


def _texture_liveness_score(face_crop: np.ndarray) -> float:
    gray = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)
    lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    high_freq = _clip01((lap_var - 20.0) / 220.0)
    hist = cv2.calcHist([gray], [0], None, [32], [0, 256]).reshape(-1)
    hist = hist / max(float(hist.sum()), 1.0)
    entropy = -float(np.sum(hist * np.log2(hist + 1e-8))) / 5.0
    return round(_clip01(high_freq * 0.55 + entropy * 0.45), 4)


def _motion_liveness_score(frame_faces: list[FrameFace] | None) -> float:
    if not frame_faces or len(frame_faces) < 3:
        return 0.3
    centers = np.asarray(
        [
            [item.face.bbox[0] + item.face.bbox[2] / 2.0, item.face.bbox[1] + item.face.bbox[3] / 2.0]
            for item in frame_faces
        ],
        dtype=np.float32,
    )
    movement = float(np.mean(np.linalg.norm(np.diff(centers, axis=0), axis=1)))
    pose_delta = max(
        float(np.ptp([item.face.yaw for item in frame_faces])),
        float(np.ptp([item.face.pitch for item in frame_faces])),
    )
    return round(_clip01(movement / 18.0 * 0.35 + pose_delta / 20.0 * 0.65), 4)


def _blink_confidence(frame_faces: list[FrameFace]) -> float:
    if len(frame_faces) < 4:
        return 0.0
    eye_scores: list[float] = []
    for item in frame_faces:
        landmarks = item.face.landmarks
        if landmarks is None or landmarks.shape[0] < 2:
            continue
        gray = cv2.cvtColor(item.face.crop, cv2.COLOR_BGR2GRAY)
        x, y, w, h = item.face.bbox
        eyes = landmarks[:2].copy()
        eyes[:, 0] -= x
        eyes[:, 1] -= y
        patch_scores = []
        for eye_x, eye_y in eyes:
            cx, cy = int(eye_x), int(eye_y)
            rx = max(3, int(w * 0.08))
            ry = max(2, int(h * 0.035))
            patch = gray[max(0, cy - ry) : min(gray.shape[0], cy + ry), max(0, cx - rx) : min(gray.shape[1], cx + rx)]
            if patch.size:
                patch_scores.append(float(np.mean(patch)))
        if patch_scores:
            eye_scores.append(float(np.mean(patch_scores)))
    if len(eye_scores) < 4:
        return 0.0
    variation = float(np.ptp(eye_scores))
    return _clip01(variation / 35.0)
