"""JSON schemas for backend integration."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


DocumentType = Literal["CCCD", "GPLX", "PASSPORT", "UNKNOWN"]
DecisionType = Literal["match", "consider", "failed"]
LivenessChallenge = Literal["turn_left", "turn_right", "look_up", "look_down", "blink"]


class QualityDetail(BaseModel):
    blur: float = Field(ge=0.0, le=1.0)
    brightness: float = Field(ge=0.0, le=1.0)
    contrast: float = Field(ge=0.0, le=1.0)
    glare: float = Field(ge=0.0, le=1.0)
    corners: float = Field(ge=0.0, le=1.0)
    screenshot: float = Field(default=1.0, ge=0.0, le=1.0)


class ParsedFields(BaseModel):
    id_number: str | None = None
    full_name: str | None = None
    date_of_birth: str | None = None
    sex: str | None = None
    nationality: str | None = None
    place_of_origin: str | None = None
    place_of_residence: str | None = None
    issue_date: str | None = None
    issue_place: str | None = None
    expiry_date: str | None = None
    license_class: str | None = None
    passport_number: str | None = None
    surname: str | None = None
    given_names: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


def parsed_fields_payload(fields: ParsedFields | None) -> dict[str, Any] | None:
    """Full extracted fields for backend review (no masking)."""
    if fields is None:
        return None

    payload = fields.model_dump()
    payload["field_presence"] = {
        key: value is not None and value != ""
        for key, value in fields.model_dump(exclude={"extra"}).items()
    }
    if fields.extra.get("document_expired") is not None:
        payload["document_expired"] = bool(fields.extra["document_expired"])
    if fields.extra.get("days_until_expiry") is not None:
        payload["days_until_expiry"] = fields.extra["days_until_expiry"]
    return payload


class FaceResult(BaseModel):
    detected: bool
    bbox: list[int] | None = None
    confidence: float | None = None
    quality_score: float | None = Field(default=None, ge=0.0, le=1.0)
    confident: bool = False
    warnings: list[str] = Field(default_factory=list)
    crop_base64: str | None = None


class OCRLine(BaseModel):
    text: str
    confidence: float
    bbox: list[list[float]] | None = None


class LLMTokenUsage(BaseModel):
    stage: Literal["extract", "review", "admin_review"] | None = None
    provider: str | None = None
    model: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class LLMUsageSummary(BaseModel):
    extract: LLMTokenUsage | None = None
    review: LLMTokenUsage | None = None
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    call_count: int = 0

    @classmethod
    def from_calls(
        cls,
        extract: LLMTokenUsage | None,
        review: LLMTokenUsage | None,
    ) -> "LLMUsageSummary":
        calls = [item for item in (extract, review) if item is not None]
        prompt = sum(item.prompt_tokens for item in calls)
        completion = sum(item.completion_tokens for item in calls)
        total = sum(item.total_tokens for item in calls)
        return cls(
            extract=extract,
            review=review,
            total_prompt_tokens=prompt,
            total_completion_tokens=completion,
            total_tokens=total,
            call_count=len(calls),
        )


class DocumentAnalysisResult(BaseModel):
    """Primary response contract for backend (Week 1)."""

    document_type: DocumentType
    ocr_confidence: float = Field(ge=0.0, le=1.0)
    image_quality_score: float = Field(ge=0.0, le=1.0)
    document_face_detected: bool
    document_face_confident: bool = False
    document_face_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    warnings: list[str] = Field(default_factory=list)
    record_id: str | None = None
    timings_ms: dict[str, float] = Field(default_factory=dict)
    llm_usage: LLMUsageSummary | None = None

    # Internal only — not returned in public API payloads
    success: bool = True
    quality_details: QualityDetail | None = None
    parsed_fields: ParsedFields | None = None
    face: FaceResult | None = None
    ocr_lines: list[OCRLine] = Field(default_factory=list)
    raw_ocr_text: str = ""

    def to_backend_json(self) -> dict[str, Any]:
        """Primary backend payload including extracted fields."""
        payload: dict[str, Any] = {
            "document_type": self.document_type,
            "ocr_confidence": round(self.ocr_confidence, 4),
            "image_quality_score": round(self.image_quality_score, 4),
            "document_face_detected": self.document_face_detected,
            "document_face_confident": self.document_face_confident,
            "document_face_confidence": (
                round(self.document_face_confidence, 4)
                if self.document_face_confidence is not None
                else None
            ),
            "parsed_fields": parsed_fields_payload(self.parsed_fields),
            "warnings": self.warnings,
        }
        if self.llm_usage is not None and self.llm_usage.call_count > 0:
            payload["llm_usage"] = self.llm_usage.model_dump()
        if self.record_id:
            payload["record_id"] = self.record_id
        return payload

    def to_full_json(self) -> dict[str, Any]:
        """Extended payload for debugging, including extracted fields."""
        face = None
        if self.face is not None:
            face = {
                "detected": self.face.detected,
                "bbox": self.face.bbox,
                "confidence": self.face.confidence,
                "quality_score": self.face.quality_score,
                "confident": self.face.confident,
                "warnings": self.face.warnings,
            }

        payload: dict[str, Any] = {
            "document_type": self.document_type,
            "ocr_confidence": round(self.ocr_confidence, 4),
            "image_quality_score": round(self.image_quality_score, 4),
            "document_face_detected": self.document_face_detected,
            "document_face_confident": self.document_face_confident,
            "document_face_confidence": (
                round(self.document_face_confidence, 4)
                if self.document_face_confidence is not None
                else None
            ),
            "warnings": self.warnings,
            "success": self.success,
            "quality_details": (
                self.quality_details.model_dump() if self.quality_details else None
            ),
            "parsed_fields": parsed_fields_payload(self.parsed_fields),
            "face": face,
            "ocr_line_count": len(self.ocr_lines),
        }
        if self.record_id:
            payload["record_id"] = self.record_id
        if self.llm_usage is not None and self.llm_usage.call_count > 0:
            payload["llm_usage"] = self.llm_usage.model_dump()
        if self.timings_ms:
            payload["timings_ms"] = self.timings_ms
        return payload


class FaceQualityDetail(BaseModel):
    blur: float = Field(ge=0.0, le=1.0)
    pose: float = Field(ge=0.0, le=1.0)
    illumination: float = Field(ge=0.0, le=1.0)
    face_coverage: float = Field(ge=0.0, le=1.0)
    centered: float = Field(ge=0.0, le=1.0)


class FaceDetectionDetail(BaseModel):
    detected: bool
    face_count: int = 0
    bbox: list[int] | None = None
    confidence: float | None = None
    embedding_model: str | None = None
    embedding_ready: bool = False
    portrait_ok: bool = False


class PassiveLivenessResult(BaseModel):
    score: float = Field(ge=0.0, le=1.0)
    passed: bool
    method: str
    warnings: list[str] = Field(default_factory=list)


class ActiveLivenessChallengeResult(BaseModel):
    challenge: LivenessChallenge
    passed: bool
    confidence: float = Field(ge=0.0, le=1.0)


class FaceMatchingResult(BaseModel):
    similarity: float | None = Field(default=None, ge=-1.0, le=1.0)
    decision: DecisionType
    thresholds: dict[str, float]
    reason: str


class FrameDeepfakeScore(BaseModel):
    frame_index: int
    score: float = Field(ge=0.0, le=1.0)
    suspicious: bool
    method: str


class DeepfakeAnalysisResult(BaseModel):
    score: float = Field(ge=0.0, le=1.0)
    mean_score: float = Field(ge=0.0, le=1.0)
    max_score: float = Field(ge=0.0, le=1.0)
    suspicious_frame_count: int
    suspicious_frames: list[int] = Field(default_factory=list)
    frames: list[FrameDeepfakeScore] = Field(default_factory=list)
    method: str
    warnings: list[str] = Field(default_factory=list)


class TemporalIdentityConsistencyResult(BaseModel):
    score: float = Field(ge=0.0, le=1.0)
    mean_drift: float | None = Field(default=None, ge=0.0, le=2.0)
    max_drift: float | None = Field(default=None, ge=0.0, le=2.0)
    suspicious_pair_count: int = 0
    embedding_frames: int = 0
    method: str
    warnings: list[str] = Field(default_factory=list)


class ReplayAttackResult(BaseModel):
    score: float = Field(ge=0.0, le=1.0)
    moire_score: float = Field(ge=0.0, le=1.0)
    flicker_score: float = Field(ge=0.0, le=1.0)
    duplication_score: float = Field(ge=0.0, le=1.0)
    duplicate_pairs: int = 0
    confirmed: bool = False
    face_motion_score: float = Field(default=0.0, ge=0.0, le=1.0)
    warnings: list[str] = Field(default_factory=list)


class CameraInjectionResult(BaseModel):
    score: float = Field(ge=0.0, le=1.0)
    metadata_score: float = Field(ge=0.0, le=1.0)
    challenge_timing_score: float = Field(ge=0.0, le=1.0)
    duplication_score: float = Field(ge=0.0, le=1.0)
    warnings: list[str] = Field(default_factory=list)


class LipSyncAnalysisResult(BaseModel):
    score: float = Field(ge=0.0, le=1.0)
    manipulation_probability: float = Field(default=0.0, ge=0.0, le=1.0)
    authenticity_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    verdict: Literal["real", "fake", "uncertain", "skipped"]
    is_fake: bool = False
    passed: bool = True
    skipped: bool = False
    method: str
    warnings: list[str] = Field(default_factory=list)
    detail: str | None = None


class VoiceChallengeResult(BaseModel):
    expected_text: str
    transcript: str
    normalized_expected: str
    normalized_transcript: str
    wer: float = Field(ge=0.0, le=1.0)
    similarity: float = Field(ge=0.0, le=1.0)
    passed: bool
    decision: DecisionType
    audio_detected: bool
    audio_duration_ms: float | None = None
    audio_rms: float | None = None
    speech_ratio: float | None = None
    method: str
    warnings: list[str] = Field(default_factory=list)


class RiskSignalEvidence(BaseModel):
    signal: str
    score: float = Field(ge=0.0, le=1.0)
    weight: float = Field(ge=0.0, le=1.0)
    contribution: float = Field(ge=0.0, le=1.0)
    threshold: float = Field(ge=0.0, le=1.0)
    triggered: bool
    reason_code: str
    method: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)


class RiskTopReason(BaseModel):
    signal: str
    reason_code: str
    score: float = Field(ge=0.0, le=1.0)
    contribution: float = Field(ge=0.0, le=1.0)
    triggered: bool
    message: str
    evidence: dict[str, Any] = Field(default_factory=dict)


class VideoRiskResult(BaseModel):
    score: float = Field(ge=0.0, le=1.0)
    decision: DecisionType
    reason_codes: list[str] = Field(default_factory=list)
    weights: dict[str, float] = Field(default_factory=dict)
    evidence: list[RiskSignalEvidence] = Field(default_factory=list)
    top_reasons: list[RiskTopReason] = Field(default_factory=list)
    deepfake: DeepfakeAnalysisResult
    temporal_identity: TemporalIdentityConsistencyResult
    replay_attack: ReplayAttackResult
    camera_injection: CameraInjectionResult
    lipsync: LipSyncAnalysisResult | None = None


class DecisionReason(BaseModel):
    code: str
    message: str
    severity: Literal["info", "warning", "block"] = "warning"
    source: str = "biometric"


class SelfieUploadResult(BaseModel):
    success: bool
    decision: DecisionType
    selfie_face: FaceDetectionDetail
    quality_score: float = Field(ge=0.0, le=1.0)
    quality_details: FaceQualityDetail
    passive_liveness: PassiveLivenessResult
    matching: FaceMatchingResult | None = None
    warnings: list[str] = Field(default_factory=list)


class VideoUploadResult(BaseModel):
    success: bool
    decision: DecisionType
    frames_analyzed: int
    face_frames: int
    challenge: LivenessChallenge | None = None
    best_frame_index: int | None = None
    best_live_face: FaceDetectionDetail | None = None
    quality_score: float = Field(ge=0.0, le=1.0)
    quality_details: FaceQualityDetail | None = None
    passive_liveness: PassiveLivenessResult
    active_liveness: list[ActiveLivenessChallengeResult] = Field(default_factory=list)
    matching: FaceMatchingResult | None = None
    voice_verification: VoiceChallengeResult | None = None
    risk: VideoRiskResult | None = None
    decision_reasons: list[DecisionReason] = Field(default_factory=list)
    evidence_artifacts: dict[str, Any] = Field(default_factory=dict)
    timings_ms: dict[str, float] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
