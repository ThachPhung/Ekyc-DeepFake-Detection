"""HTTP API for backend integration."""

from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile, WebSocket
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from starlette.websockets import WebSocketDisconnect

from ekyc_document.biometric import BiometricPipeline
from ekyc_document.config import PipelineConfig
from ekyc_document.liveness.frame_selection import parse_client_frame_metrics
from ekyc_document.llm_extract import LLMFieldExtractor
from ekyc_document.llm_admin_review import LLMAdminDecisionReviewer
from ekyc_document.llm_usage_metrics import llm_usage_metrics, record_llm_usage
from ekyc_document.pipeline import DocumentPipeline
from ekyc_document.private_store import PrivateRecordNotFound, PrivateRecordStore
from ekyc_document.schemas import DocumentType, LivenessChallenge
from ekyc_document.speech import SpeechVerifier

app = FastAPI(
    title="eKYC Document AI Service",
    version="1.1.0",
    description="Document OCR + biometric face matching/liveness service",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("EKYC_CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_pipeline: DocumentPipeline | None = None
_private_store: PrivateRecordStore | None = None
_biometric_pipeline: BiometricPipeline | None = None
_speech_verifier: SpeechVerifier | None = None
_CODE_DIR = Path(__file__).resolve().parents[2]
_RESULT_RECORD_DIR = _CODE_DIR / "data" / "record"
_REQUEST_METRICS: dict[str, object] = {
    "requests": 0,
    "errors": 0,
    "last_request_ms": None,
}
_VOICE_PAYLOAD_KEYS = {
    "expected_text",
    "transcript",
    "normalized_expected",
    "normalized_transcript",
    "wer",
    "similarity",
    "passed",
    "decision",
    "audio_detected",
    "audio_duration_ms",
    "audio_rms",
    "speech_ratio",
    "method",
    "warnings",
}


@app.middleware("http")
async def track_request_metrics(request, call_next):
    started = time.perf_counter()
    _REQUEST_METRICS["requests"] = int(_REQUEST_METRICS["requests"]) + 1
    try:
        response = await call_next(request)
        if response.status_code >= 500:
            _REQUEST_METRICS["errors"] = int(_REQUEST_METRICS["errors"]) + 1
        return response
    except Exception:
        _REQUEST_METRICS["errors"] = int(_REQUEST_METRICS["errors"]) + 1
        raise
    finally:
        _REQUEST_METRICS["last_request_ms"] = round((time.perf_counter() - started) * 1000, 2)


def get_pipeline() -> DocumentPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = DocumentPipeline(PipelineConfig())
    return _pipeline


def get_private_store() -> PrivateRecordStore:
    global _private_store
    if _private_store is None:
        _private_store = PrivateRecordStore(PipelineConfig())
    return _private_store


def get_biometric_pipeline() -> BiometricPipeline:
    global _biometric_pipeline
    if _biometric_pipeline is None:
        _biometric_pipeline = BiometricPipeline(PipelineConfig())
    return _biometric_pipeline


def get_speech_verifier() -> SpeechVerifier:
    global _speech_verifier
    if _speech_verifier is None:
        _speech_verifier = SpeechVerifier(PipelineConfig())
    return _speech_verifier


def require_internal_api_key(
    x_internal_api_key: str | None = Header(default=None, alias="X-Internal-API-Key"),
) -> None:
    expected = PipelineConfig().internal_api_key
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="EKYC_INTERNAL_API_KEY chưa được cấu hình trên AI service.",
        )
    if x_internal_api_key != expected:
        raise HTTPException(status_code=403, detail="API key nội bộ không hợp lệ.")


@app.get("/health")
def health() -> dict[str, object]:
    config = PipelineConfig()
    onnx = get_biometric_pipeline().onnx_registry
    missing = onnx.ensure_required_models()
    smoke = onnx.smoke_test()
    speech = get_speech_verifier().diagnostics()
    llm = LLMFieldExtractor(PipelineConfig()).diagnostics()
    smoke_ready = bool(smoke["ready"])
    status = "ok" if not missing and smoke_ready else "degraded"
    if config.require_onnx_models and (missing or not smoke_ready):
        status = "unhealthy"
    return {
        "status": status,
        "service": "ekyc-document-ai",
        "version": app.version,
        "ocr_engine": config.ocr_engine,
        "prefer_onnx": config.prefer_onnx,
        "missing_onnx_models": missing,
        "risk_weights": config.video_risk_weights,
        "video_sampling": {
            "adaptive": config.adaptive_video_sampling,
            "stride": config.video_frame_stride,
            "target_samples": config.target_video_samples,
            "max_frames": config.max_video_frames,
        },
        "onnx": onnx.diagnostics(),
        "onnx_smoke": smoke,
        "speech": speech,
        "llm_extract": llm,
        "llm_admin_review": LLMAdminDecisionReviewer().diagnostics(),
        "llm_usage_totals": llm_usage_metrics(),
        "request_metrics": dict(_REQUEST_METRICS),
    }


@app.get("/api/v1/diagnostics")
def diagnostics(_: None = Depends(require_internal_api_key)) -> dict[str, object]:
    return {
        "service": "ekyc-document-ai",
        "document": {
            "ocr_engine": get_pipeline().config.ocr_engine,
            "ocr": get_pipeline().ocr.diagnostics(),
            "face_detector": get_pipeline().config.face_detector,
            "models_dir": str(get_pipeline().config.models_dir),
        },
        "biometric": get_biometric_pipeline().diagnostics(),
        "speech": get_speech_verifier().diagnostics(),
        "llm_extract": LLMFieldExtractor(PipelineConfig()).diagnostics(),
        "llm_admin_review": LLMAdminDecisionReviewer().diagnostics(),
        "llm_usage_totals": llm_usage_metrics(),
    }


def _is_image(file: UploadFile) -> bool:
    return bool(file.content_type and file.content_type.startswith("image/"))


def _is_video(file: UploadFile) -> bool:
    return bool(file.content_type and file.content_type.startswith("video/"))


def _has_video_extension(file: UploadFile) -> bool:
    return Path(file.filename or "").suffix.lower() in {
        ".mp4",
        ".mov",
        ".webm",
        ".avi",
        ".mkv",
    }


def _overall_ekyc_decision(
    *,
    front_face_detected: bool,
    front_face_confident: bool,
    video_decision: str | None,
) -> Literal["match", "consider", "failed"]:
    if not front_face_detected or video_decision is None or video_decision == "failed":
        return "failed"
    if not front_face_confident or video_decision == "consider":
        return "consider"
    return "match"


def _back_document_json(result) -> dict[str, object]:
    """Return only back-side CCCD issue fields for legacy contract tests."""
    fields = result.parsed_fields
    parsed: dict[str, object] = {}
    if fields is not None:
        if fields.issue_date:
            parsed["issue_date"] = fields.issue_date
        issued_by = fields.extra.get("issued_by") or fields.issue_place
        if issued_by:
            parsed["issued_by"] = issued_by
    return {
        "document_type": result.document_type,
        "ocr_confidence": result.ocr_confidence,
        "image_quality_score": result.image_quality_score,
        "parsed_fields": parsed,
        "warnings": result.warnings,
    }


def _write_result_record(payload: dict, *, prefix: str = "ekyc-document") -> dict:
    _RESULT_RECORD_DIR.mkdir(parents=True, exist_ok=True)
    saved_payload = dict(payload)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    file_name = f"{prefix}-{timestamp}-{uuid.uuid4().hex[:8]}.json"
    path = _RESULT_RECORD_DIR / file_name
    saved_payload["result_file"] = str(path)
    path.write_text(
        json.dumps(saved_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return saved_payload


def _extract_voice_payload(payload: dict) -> dict | None:
    voice = payload.get("voice_verification")
    if voice is None and isinstance(payload.get("video"), dict):
        voice = payload["video"].get("voice_verification")
    if voice is None and {
        "expected_text",
        "transcript",
        "wer",
        "passed",
        "decision",
    }.issubset(payload):
        voice = {
            key: payload[key]
            for key in _VOICE_PAYLOAD_KEYS
            if key in payload
        }
    return voice if isinstance(voice, dict) else None


def _write_private_result_record(payload: dict, *, record_type: str) -> dict:
    record_id, path = get_private_store().save_result_record(
        record_type=record_type,
        payload=payload,
    )
    risk = payload.get("risk")
    if risk is None and isinstance(payload.get("video"), dict):
        risk = payload["video"].get("risk")
    voice = _extract_voice_payload(payload)
    reason_codes = risk.get("reason_codes", []) if isinstance(risk, dict) else []
    if isinstance(voice, dict) and voice.get("decision") == "failed":
        if "voice_mismatch" not in reason_codes:
            reason_codes = [*reason_codes, "voice_mismatch"]
    decision_reasons = payload.get("decision_reasons")
    if decision_reasons is None and isinstance(payload.get("video"), dict):
        decision_reasons = payload["video"].get("decision_reasons")
    decision_reason_codes = [
        item.get("code")
        for item in decision_reasons or []
        if isinstance(item, dict) and item.get("code")
    ]
    if isinstance(voice, dict) and voice.get("decision") == "failed":
        if "voice_mismatch" not in decision_reason_codes:
            decision_reason_codes = [*decision_reason_codes, "voice_mismatch"]
    compact = {
        "success": payload.get("success"),
        "decision": payload.get("decision"),
        "record_id": record_id,
        "result_file": str(path),
        "risk_score": risk.get("score") if isinstance(risk, dict) else None,
        "reason_codes": reason_codes,
        "decision_reasons": decision_reason_codes,
        "top_reasons": risk.get("top_reasons", []) if isinstance(risk, dict) else [],
        "message": "Kết quả chi tiết đã được lưu vào data/private/records.",
    }
    if isinstance(voice, dict):
        compact["voice_passed"] = voice.get("passed")
        compact["voice_wer"] = voice.get("wer")
        compact["voice_decision"] = voice.get("decision")
    return compact


def _build_ai_summary(document_result, video_result) -> dict:
    risk = video_result.risk
    matching = video_result.matching
    return {
        "document": {
            "document_type": document_result.document_type,
            "ocr_confidence": document_result.ocr_confidence,
            "image_quality_score": document_result.image_quality_score,
            "document_face_detected": document_result.document_face_detected,
            "document_face_confident": document_result.document_face_confident,
        },
        "biometric": {
            "quality_score": video_result.quality_score,
            "passive_liveness_score": video_result.passive_liveness.score,
            "passive_liveness_passed": video_result.passive_liveness.passed,
            "active_liveness": [item.model_dump() for item in video_result.active_liveness],
            "face_similarity": matching.similarity if matching is not None else None,
            "face_match_decision": matching.decision if matching is not None else None,
            "voice_verification": (
                video_result.voice_verification.model_dump()
                if video_result.voice_verification is not None
                else None
            ),
            "decision_reasons": [
                item.model_dump() for item in video_result.decision_reasons
            ],
            "evidence_artifacts": video_result.evidence_artifacts,
        },
        "risk": (
            {
                "score": risk.score,
                "decision": risk.decision,
                "reason_codes": risk.reason_codes,
                "top_reasons": [item.model_dump() for item in risk.top_reasons],
                "weights": risk.weights,
                "evidence": [item.model_dump() for item in risk.evidence],
            }
            if risk is not None
            else None
        ),
    }


@app.post("/api/v1/document/analyze")
async def analyze_document_endpoint(
    file: UploadFile | None = File(
        default=None,
        description="Ảnh giấy tờ (JPEG/PNG). Tương thích client cũ, dùng như mặt trước.",
    ),
    front_file: UploadFile | None = File(
        default=None, description="Ảnh mặt trước giấy tờ (JPEG/PNG)"
    ),
    back_file: UploadFile | None = File(
        default=None, description="Ảnh mặt sau CCCD để trích ngày cấp/nơi cấp"
    ),
    document_type: DocumentType | None = Form(
        default=None, description="Gợi ý loại giấy tờ: CCCD | GPLX | PASSPORT"
    ),
    response_format: Literal["compact", "full"] = Form(
        default="compact",
        description="compact = contract tuần 1; full = chi tiết đầy đủ",
    ),
    include_face_crop: bool = Form(default=False),
) -> dict:
    front_upload = front_file or file
    if front_upload is None:
        raise HTTPException(
            status_code=400,
            detail="Thiếu ảnh mặt trước. Gửi field 'file' hoặc 'front_file'.",
        )

    content = await _read_image_upload(front_upload, label="Ảnh mặt trước")
    back_content = None
    if back_file is not None:
        back_content = await _read_image_upload(back_file, label="Ảnh mặt sau")

    try:
        result = get_pipeline().analyze_two_sides(
            content,
            back_content,
            document_type_hint=document_type,
            include_face_crop=include_face_crop,
            save_private_record=True,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"AI pipeline error: {exc}") from exc

    payload = result.to_full_json() if response_format == "full" else result.to_backend_json()
    record_llm_usage(result.llm_usage)
    return _write_result_record(payload)


async def _read_image_upload(upload: UploadFile, *, label: str) -> bytes:
    if not upload.content_type or not upload.content_type.startswith("image/"):
        raise HTTPException(
            status_code=400,
            detail=f"{label} phải là ảnh (image/jpeg, image/png).",
        )

    content = await upload.read()
    if not content:
        raise HTTPException(status_code=400, detail=f"{label} rỗng.")
    return content


async def _read_video_upload(upload: UploadFile, *, label: str) -> bytes:
    if not _is_video(upload) and not _has_video_extension(upload):
        raise HTTPException(
            status_code=400,
            detail=f"{label} phải là video (.mp4, .mov, .webm, .avi, .mkv).",
        )

    content = await upload.read()
    if not content:
        raise HTTPException(status_code=400, detail=f"{label} rỗng.")
    return content


def _parse_client_frame_scores(raw: str | None) -> list:
    if raw is None or not raw.strip():
        return []

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=422,
            detail="client_frame_scores phải là JSON array hợp lệ.",
        ) from exc

    return parse_client_frame_metrics(payload)


def _parse_best_frame_progress(raw: str | None) -> float | None:
    if raw is None or not raw.strip():
        return None

    try:
        progress = float(raw)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail="best_frame_progress phải là số thực trong khoảng 0..1.",
        ) from exc

    if progress < 0.0 or progress > 1.0:
        raise HTTPException(
            status_code=422,
            detail="best_frame_progress phải nằm trong khoảng 0..1.",
        )
    return progress


def _parse_optional_score(raw: str | None) -> float | None:
    if raw is None or not raw.strip():
        return None
    try:
        score = float(raw)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail="client_passive_liveness_score phải là số thực trong khoảng 0..1.",
        ) from exc
    if score < 0.0 or score > 1.0:
        raise HTTPException(
            status_code=422,
            detail="client_passive_liveness_score phải nằm trong khoảng 0..1.",
        )
    return score


def _parse_best_frame_index(raw: str | None) -> int | None:
    if raw is None or not raw.strip():
        return None

    try:
        frame_index = int(raw)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail="best_frame_index phải là số nguyên không âm.",
        ) from exc

    if frame_index < 0:
        raise HTTPException(status_code=422, detail="best_frame_index phải >= 0.")
    return frame_index


@app.post("/video/upload")
@app.post("/api/v1/video/upload")
async def upload_video_endpoint(
    file: UploadFile = File(description="Video chân dung live"),
    doc_face: UploadFile = File(description="Ảnh giấy tờ/ảnh chân dung để matching"),
    challenge: LivenessChallenge | None = Form(default=None),
    expected_text: str | None = Form(
        default=None,
        description="Câu user phải đọc trong video (speech challenge).",
    ),
    best_frame_index: str | None = Form(
        default=None,
        description="Chỉ số frame client chọn (MediaPipe), tuỳ chọn nếu đã gửi best_frame_progress.",
    ),
    best_frame_progress: str | None = Form(
        default=None,
        description="Vị trí 0..1 trong timeline video nơi client chọn best frame (MediaPipe).",
    ),
    client_frame_scores: str | None = Form(
        default=None,
        description="JSON array điểm chất lượng frame từ MediaPipe Face Mesh trên web.",
    ),
    client_passive_liveness_score: str | None = Form(
        default=None,
        description="Điểm MiniFASNet INT8 chạy WASM trên browser (0..1).",
    ),
    client_transcript: str | None = Form(
        default=None,
        description="Transcript streaming ASR từ browser (ViStreamASR client).",
    ),
) -> dict:
    video_content = await _read_video_upload(file, label="Video")
    doc_face_content = await _read_image_upload(doc_face, label="Ảnh giấy tờ")

    try:
        result = get_biometric_pipeline().analyze_video(
            video_content,
            doc_face_content,
            challenge=challenge,
            expected_text=expected_text,
            client_best_frame_index=_parse_best_frame_index(best_frame_index),
            client_best_frame_progress=_parse_best_frame_progress(best_frame_progress),
            client_frame_metrics=_parse_client_frame_scores(client_frame_scores),
            client_passive_liveness_score=_parse_optional_score(client_passive_liveness_score),
            client_transcript=client_transcript.strip() if client_transcript else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"AI video pipeline error: {exc}") from exc

    return _write_private_result_record(
        result.model_dump(),
        record_type="ekyc-video",
    )


@app.post("/api/v1/selfie/upload")
async def upload_selfie_endpoint(
    file: UploadFile = File(description="Ảnh selfie chân dung"),
    doc_face: UploadFile = File(description="Ảnh giấy tờ/ảnh chân dung để matching"),
) -> dict:
    selfie_content = await _read_image_upload(file, label="Selfie")
    doc_face_content = await _read_image_upload(doc_face, label="Ảnh giấy tờ")

    try:
        result = get_biometric_pipeline().analyze_selfie(selfie_content, doc_face_content)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"AI selfie pipeline error: {exc}") from exc

    return _write_private_result_record(
        result.model_dump(),
        record_type="ekyc-selfie",
    )


@app.get("/api/v1/voice/challenge")
def voice_challenge_endpoint(
    seed: int | None = None,
) -> dict[str, str]:
    return get_speech_verifier().generate_voice_challenge(seed=seed)


@app.websocket("/api/v1/voice/stream")
async def voice_stream_endpoint(websocket: WebSocket) -> None:
    """
    Streaming ASR WebSocket — gửi PCM int16 mono 16kHz theo chunk ~640ms.
    JSON config: {"type":"config","expected_text":"..."}
    JSON finalize: {"type":"finalize"}
    """
    await websocket.accept()
    verifier = get_speech_verifier()
    session = verifier.create_stream_session()
    expected_text: str | None = None

    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break

            if message.get("bytes"):
                result = session.ingest_pcm16(message["bytes"])
                if result is not None:
                    await websocket.send_json(
                        {
                            "type": "partial" if result.partial else "final",
                            "text": result.text,
                            "method": result.method,
                        }
                    )
                continue

            raw_text = message.get("text")
            if not raw_text:
                continue

            payload = json.loads(raw_text)
            msg_type = payload.get("type")
            if msg_type == "config":
                expected_text = str(payload.get("expected_text") or "").strip() or None
                await websocket.send_json({"type": "ready", "chunk_size_ms": 640})
                continue

            if msg_type == "finalize":
                transcript, method = session.finalize()
                response: dict[str, object] = {
                    "type": "final",
                    "text": transcript,
                    "method": method,
                }
                if expected_text:
                    verification = verifier.verify_transcript(
                        expected_text,
                        transcript,
                        method=method,
                    )
                    response["verification"] = verification.model_dump()
                    response["success"] = verification.passed
                    response["decision"] = verification.decision
                await websocket.send_json(response)
    except WebSocketDisconnect:
        return


@app.post("/api/v1/voice/verify")
async def verify_voice_endpoint(
    file: UploadFile = File(description="Video hoặc audio chứa giọng nói"),
    expected_text: str = Form(description="Câu challenge user phải đọc"),
) -> dict:
    if not expected_text.strip():
        raise HTTPException(status_code=400, detail="expected_text không được rỗng.")

    content_type = (file.content_type or "").lower()
    filename = (file.filename or "").lower()
    is_video = content_type.startswith("video/") or filename.endswith(
        (".mp4", ".mov", ".webm", ".avi", ".mkv")
    )
    is_audio = content_type.startswith("audio/") or filename.endswith(
        (".wav", ".mp3", ".m4a", ".aac", ".ogg", ".flac")
    )
    if not is_video and not is_audio:
        raise HTTPException(
            status_code=400,
            detail="File phải là video hoặc audio.",
        )

    media_content = await file.read()
    if not media_content:
        raise HTTPException(status_code=400, detail="File rỗng.")

    try:
        verifier = get_speech_verifier()
        if is_audio:
            result = verifier.verify_audio(media_content, expected_text.strip())
        else:
            result = verifier.verify_video(media_content, expected_text.strip())
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Speech verification error: {exc}") from exc

    full_payload = {
        **result.model_dump(),
        "success": result.passed,
        "decision": result.decision,
    }
    compact = _write_private_result_record(
        full_payload,
        record_type="ekyc-voice",
    )
    return {
        **compact,
        "expected_text": result.expected_text,
        "transcript": result.transcript,
        "normalized_expected": result.normalized_expected,
        "normalized_transcript": result.normalized_transcript,
        "wer": result.wer,
        "similarity": result.similarity,
        "passed": result.passed,
        "audio_detected": result.audio_detected,
        "audio_duration_ms": result.audio_duration_ms,
        "audio_rms": result.audio_rms,
        "speech_ratio": result.speech_ratio,
        "method": result.method,
        "warnings": result.warnings,
    }


@app.post("/api/v1/ekyc/verify")
async def verify_ekyc_endpoint(
    front_file: UploadFile = File(description="Ảnh mặt trước giấy tờ"),
    back_file: UploadFile = File(description="Ảnh mặt sau giấy tờ"),
    video_file: UploadFile = File(description="Video chân dung live"),
    document_type: DocumentType | None = Form(default="CCCD"),
    challenge: LivenessChallenge | None = Form(default=None),
    expected_text: str | None = Form(
        default=None,
        description="Câu user phải đọc trong video (speech challenge).",
    ),
    best_frame_index: str | None = Form(default=None),
    best_frame_progress: str | None = Form(default=None),
    client_frame_scores: str | None = Form(default=None),
) -> dict:
    total_started = time.perf_counter()
    front_content = await _read_image_upload(front_file, label="Ảnh mặt trước")
    back_content = await _read_image_upload(back_file, label="Ảnh mặt sau")
    video_content = await _read_video_upload(video_file, label="Video")

    try:
        document_result = get_pipeline().analyze_two_sides(
            front_content,
            back_content,
            document_type_hint=document_type,
            include_face_crop=False,
            save_private_record=True,
        )
        video_result = get_biometric_pipeline().analyze_video(
            video_content,
            front_content,
            challenge=challenge,
            expected_text=expected_text,
            client_best_frame_index=_parse_best_frame_index(best_frame_index),
            client_best_frame_progress=_parse_best_frame_progress(best_frame_progress),
            client_frame_metrics=_parse_client_frame_scores(client_frame_scores),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"AI eKYC pipeline error: {exc}") from exc

    payload = {
        "success": video_result.decision == "match",
        "decision": _overall_ekyc_decision(
            front_face_detected=document_result.document_face_detected,
            front_face_confident=document_result.document_face_confident,
            video_decision=video_result.decision,
        ),
        "similarity": (
            video_result.matching.similarity if video_result.matching is not None else None
        ),
        "front_document": document_result.to_full_json(),
        "video": video_result.model_dump(),
        "ai_summary": _build_ai_summary(document_result, video_result),
        "warnings": [*document_result.warnings, *video_result.warnings],
    }
    payload["timings_ms"] = {
        "document_total": document_result.timings_ms.get("total", 0.0),
        "video_total": video_result.timings_ms.get("total", 0.0),
        "api_total": round((time.perf_counter() - total_started) * 1000.0, 2),
    }
    payload["success"] = payload["decision"] == "match"
    return _write_private_result_record(payload, record_type="ekyc-verify")


@app.post("/api/v1/document/analyze/full")
async def analyze_document_full(
    file: UploadFile | None = File(default=None),
    front_file: UploadFile | None = File(default=None),
    back_file: UploadFile | None = File(default=None),
    document_type: DocumentType | None = Form(default=None),
    include_face_crop: bool = Form(default=False),
) -> dict:
    return await analyze_document_endpoint(
        file=file,
        front_file=front_file,
        back_file=back_file,
        document_type=document_type,
        response_format="full",
        include_face_crop=include_face_crop,
    )


@app.get("/api/v1/document/records/{record_id}")
def get_private_record(
    record_id: str,
    _: None = Depends(require_internal_api_key),
) -> dict:
    """Đọc thông tin cá nhân đã lưu riêng — chỉ backend nội bộ."""
    try:
        return get_private_store().load_record(record_id)
    except PrivateRecordNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


class AdminReviewAssistRequest(BaseModel):
    case_summary: dict[str, Any] | None = None
    unified_result: dict[str, Any] | None = None


@app.post("/api/v1/admin/review-assist")
def admin_review_assist(
    payload: AdminReviewAssistRequest,
    _: None = Depends(require_internal_api_key),
) -> dict[str, Any]:
    """LLM summary to support human admin approve/reject decisions."""
    reviewer = LLMAdminDecisionReviewer()
    if payload.unified_result:
        review = reviewer.review_unified_result(payload.unified_result)
    elif payload.case_summary:
        review = reviewer.review_case(payload.case_summary)
    else:
        raise HTTPException(
            status_code=422,
            detail="Cần case_summary hoặc unified_result trong body JSON.",
        )
    return review.model_dump(mode="json")
