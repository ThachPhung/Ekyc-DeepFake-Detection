"""Redis-backed OCR worker for two-sided document eKYC requests."""

from __future__ import annotations

import hmac
import html
import json
import logging
import os
import smtplib
import ssl
import time
import uuid
from datetime import datetime, timezone
from email.message import EmailMessage
from hashlib import sha256
from pathlib import Path
from typing import Any
from urllib.parse import quote

try:
    import psycopg
except ModuleNotFoundError:  # pragma: no cover - exercised in minimal test envs
    psycopg = None  # type: ignore[assignment]

try:
    import redis
except ModuleNotFoundError:  # pragma: no cover - exercised in minimal test envs
    redis = None  # type: ignore[assignment]

from ekyc_document.biometric import BiometricPipeline
from ekyc_document.config import PipelineConfig
from ekyc_document.llm_admin_review import LLMAdminDecisionReviewer
from ekyc_document.pipeline import DocumentPipeline

try:
    from psycopg.types.json import Jsonb
except ModuleNotFoundError:  # pragma: no cover - exercised in minimal test envs

    def Jsonb(value: Any) -> Any:
        return value

from worker.crypto import encrypt_document_payload
from worker.masking import mask_document_payload

logger = logging.getLogger("ekyc_worker")

QUEUE_NAME = os.getenv("EKYC_QUEUE_NAME", "ekyc:ocr:jobs")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
MAX_RETRIES = int(os.getenv("EKYC_WORKER_MAX_RETRIES", "3"))
RETRY_DELAY_SECONDS = float(os.getenv("EKYC_WORKER_RETRY_DELAY_SECONDS", "2"))
MODEL_VERSION = os.getenv("AI_MODEL_VERSION", "ocr-id-card-two-sides-v1")


def _require_psycopg():
    if psycopg is None:
        raise RuntimeError("Missing dependency: install psycopg[binary] to run eKYC worker DB writes.")
    return psycopg


def _require_redis():
    if redis is None:
        raise RuntimeError("Missing dependency: install redis to run eKYC worker queue consumer.")
    return redis


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _render_ekyc_verified_email_html(
    *,
    project_name: str,
    display_name: str,
    profile_link: str,
) -> str:
    template_path = (
        Path(__file__).resolve().parents[2]
        / "backend"
        / "app"
        / "email-templates"
        / "src"
        / "ekyc_verified.html"
    )
    context = {
        "project_name": html.escape(project_name),
        "username": html.escape(display_name),
        "link": html.escape(profile_link, quote=True),
    }
    if template_path.exists():
        html_content = template_path.read_text(encoding="utf-8")
        for key, value in context.items():
            html_content = html_content.replace(f"{{{{ {key} }}}}", value)
        return html_content

    return f"""
    <html>
      <body>
        <p>Hi {context["username"]},</p>
        <p>Your eKYC verification has been approved.</p>
        <p>You can now use verified account features.</p>
        <p><a href="{context["link"]}">View your profile</a></p>
      </body>
    </html>
    """


def _send_ekyc_verified_email(*, email_to: str, full_name: str | None = None) -> None:
    smtp_host = os.getenv("SMTP_HOST")
    from_email = os.getenv("EMAILS_FROM_EMAIL")
    if not smtp_host or not from_email:
        logger.info("Skipping eKYC verification email; SMTP is not configured")
        return

    project_name = os.getenv("PROJECT_NAME", "VinTrade")
    from_name = os.getenv("EMAILS_FROM_NAME") or project_name
    frontend_host = os.getenv("FRONTEND_HOST", "http://localhost:3060").rstrip("/")
    profile_link = f"{frontend_host}/profile"
    display_name = (full_name or "").strip() or "there"
    subject = f"{project_name} - eKYC verification approved"
    html_content = _render_ekyc_verified_email_html(
        project_name=project_name,
        display_name=display_name,
        profile_link=profile_link,
    )

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"{from_name} <{from_email}>"
    message["To"] = email_to
    message.set_content(
        "\n".join(
            [
                f"Hi {display_name},",
                "",
                "Your eKYC verification has been approved.",
                "You can now use verified account features.",
                "",
                f"View your profile: {profile_link}",
            ]
        )
    )
    message.add_alternative(html_content, subtype="html")

    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    smtp_tls = _env_bool("SMTP_TLS", True)
    smtp_ssl = _env_bool("SMTP_SSL", False)

    if smtp_ssl:
        with smtplib.SMTP_SSL(
            smtp_host,
            smtp_port,
            context=ssl.create_default_context(),
            timeout=10,
        ) as smtp:
            if smtp_user:
                smtp.login(smtp_user, smtp_password or "")
            smtp.send_message(message)
        return

    with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as smtp:
        if smtp_tls:
            smtp.starttls(context=ssl.create_default_context())
        if smtp_user:
            smtp.login(smtp_user, smtp_password or "")
        smtp.send_message(message)


def _ai_document_type(document_type: str | None) -> str:
    if document_type == "HOCHIEU":
        return "PASSPORT"
    if document_type in {"CCCD", "GPLX", "PASSPORT"}:
        return document_type
    return "CCCD"


def _public_document_type(document_type: str | None) -> str | None:
    if document_type == "PASSPORT":
        return "HOCHIEU"
    return document_type


def _database_url() -> str:
    host = os.getenv("POSTGRES_SERVER", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = quote(os.getenv("POSTGRES_DB", "app").lstrip("/"), safe="")
    user = quote(os.getenv("POSTGRES_USER", "postgres"), safe="")
    password = quote(os.getenv("POSTGRES_PASSWORD", ""), safe="")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


def _update_request(
    *,
    request_id: str,
    status: str,
    ocr_result: dict[str, Any] | None = None,
    error_message: str | None = None,
    processed: bool = False,
) -> None:
    processed_at = datetime.now(timezone.utc) if processed else None
    with _require_psycopg().connect(_database_url()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE ekyc_sessions
                SET status = %s,
                    model_version = %s,
                    updated_at = NOW(),
                    processed_at = COALESCE(%s, processed_at)
                WHERE request_id = %s
                """,
                (
                    status,
                    MODEL_VERSION,
                    processed_at,
                    request_id,
                ),
            )
            cur.execute(
                """
                UPDATE ekyc_ocr_results
                SET status = %s,
                    ocr_result = %s,
                    error_message = %s,
                    model_version = %s,
                    started_at = COALESCE(started_at, NOW()),
                    completed_at = COALESCE(%s, completed_at)
                WHERE id = (
                    SELECT r.id
                    FROM ekyc_ocr_results r
                    JOIN ekyc_sessions s ON s.id = r.session_id
                    WHERE s.request_id = %s
                    ORDER BY r.created_at DESC
                    LIMIT 1
                )
                """,
                (
                    status,
                    Jsonb(ocr_result) if ocr_result is not None else None,
                    error_message,
                    MODEL_VERSION,
                    processed_at,
                    request_id,
                ),
            )
        conn.commit()


def _update_unified_request(
    *,
    request_id: str,
    status: str,
    result: dict[str, Any] | None = None,
    score: float | None = None,
    confidence: float | None = None,
    decision: str | None = None,
    error_message: str | None = None,
    processed: bool = False,
) -> None:
    processed_at = datetime.now(timezone.utc) if processed else None
    with _require_psycopg().connect(_database_url()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE ekyc_sessions
                SET status = %s,
                    result = %s,
                    score = %s,
                    confidence = %s,
                    decision = %s,
                    error_message = %s,
                    model_version = %s,
                    updated_at = NOW(),
                    processed_at = COALESCE(%s, processed_at)
                WHERE request_id = %s
                """,
                (
                    status,
                    Jsonb(result) if result is not None else None,
                    score,
                    confidence,
                    decision,
                    error_message,
                    MODEL_VERSION,
                    processed_at,
                    request_id,
                ),
            )
        conn.commit()


def _identity_number_hash(identity_number: str) -> str:
    key = (
        os.getenv("EKYC_IDENTITY_HASH_KEY")
        or os.getenv("SECRET_KEY")
        or "dev-ekyc-identity-hash-key"
    )
    normalized = "".join(identity_number.split()).upper()
    return hmac.new(key.encode("utf-8"), normalized.encode("utf-8"), sha256).hexdigest()


def _save_ekyc_result(
    *,
    request_id: str,
    status: str,
    result: dict[str, Any],
    document_result: dict[str, Any],
    liveness_result: dict[str, Any],
    voice_result: dict[str, Any],
    score: float | None,
    confidence: float | None,
    decision: str,
    error_message: str | None,
    encrypted_document_result: str | None = None,
) -> tuple[str, str | None]:
    completed_at = datetime.now(timezone.utc)
    with _require_psycopg().connect(_database_url()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, user_id
                FROM ekyc_sessions
                WHERE request_id = %s
                """,
                (request_id,),
            )
            row = cur.fetchone()
            if row is None:
                raise ValueError(f"Cannot save result; eKYC request not found: {request_id}")

            session_id, user_id = row
            cur.execute(
                """
                INSERT INTO ekyc_results (
                    id, session_id, user_id, status, decision, score, confidence,
                    document_result, encrypted_document_result,
                    liveness_result, voice_result, raw_result,
                    error_message, model_version, created_at, completed_at
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s
                )
                ON CONFLICT ON CONSTRAINT uq_ekyc_results_session_id
                DO UPDATE SET
                    user_id = EXCLUDED.user_id,
                    status = EXCLUDED.status,
                    decision = EXCLUDED.decision,
                    score = EXCLUDED.score,
                    confidence = EXCLUDED.confidence,
                    document_result = EXCLUDED.document_result,
                    encrypted_document_result = EXCLUDED.encrypted_document_result,
                    liveness_result = EXCLUDED.liveness_result,
                    voice_result = EXCLUDED.voice_result,
                    raw_result = EXCLUDED.raw_result,
                    error_message = EXCLUDED.error_message,
                    model_version = EXCLUDED.model_version,
                    completed_at = EXCLUDED.completed_at
                RETURNING id
                """,
                (
                    uuid.uuid4(),
                    session_id,
                    user_id,
                    status,
                    decision,
                    score,
                    confidence,
                    Jsonb(document_result),
                    encrypted_document_result,
                    Jsonb(liveness_result),
                    Jsonb(voice_result),
                    Jsonb(result),
                    error_message,
                    MODEL_VERSION,
                    completed_at,
                ),
            )
            result_row = cur.fetchone()
            if result_row is None:
                raise ValueError(f"Cannot save eKYC result for request: {request_id}")
            result_id = result_row[0]
        conn.commit()
    return str(result_id), str(user_id) if user_id is not None else None


def _save_verified_identity(
    *,
    user_id: str,
    result_id: str,
    document_result: dict[str, Any],
) -> tuple[bool, str | None, str | None]:
    parsed_fields = document_result.get("parsed_fields")
    fields = parsed_fields if isinstance(parsed_fields, dict) else document_result
    identity_number = str(
        fields.get("id_number") or fields.get("passport_number") or ""
    ).strip()
    if not identity_number:
        return False, None, None

    now = datetime.now(timezone.utc)
    identity_hash = _identity_number_hash(identity_number)
    with _require_psycopg().connect(_database_url()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT u.email, u.full_name, vi.id
                FROM "user" u
                LEFT JOIN verified_identities vi
                    ON vi.ekyc_result_id = %s
                    AND vi.revoked_at IS NULL
                WHERE u.id = %s
                """,
                (result_id, user_id),
            )
            existing_row = cur.fetchone()
            email_to = str(existing_row[0]) if existing_row and existing_row[0] else None
            full_name = str(existing_row[1]) if existing_row and existing_row[1] else None
            already_verified = bool(existing_row and existing_row[2] is not None)

            cur.execute(
                """
                INSERT INTO verified_identities (
                    id, user_id, ekyc_result_id, document_type,
                    identity_number_hash, identity_number_encrypted,
                    full_name, birth_date, gender,
                    nationality, issued_date, expired_date, verified_at,
                    created_at, updated_at
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW()
                )
                ON CONFLICT ON CONSTRAINT uq_verified_identities_ekyc_result_id
                DO UPDATE SET
                    user_id = EXCLUDED.user_id,
                    document_type = EXCLUDED.document_type,
                    identity_number_hash = EXCLUDED.identity_number_hash,
                    identity_number_encrypted = EXCLUDED.identity_number_encrypted,
                    full_name = EXCLUDED.full_name,
                    birth_date = EXCLUDED.birth_date,
                    gender = EXCLUDED.gender,
                    nationality = EXCLUDED.nationality,
                    issued_date = EXCLUDED.issued_date,
                    expired_date = EXCLUDED.expired_date,
                    verified_at = EXCLUDED.verified_at,
                    revoked_at = NULL,
                    updated_at = NOW()
                """,
                (
                    uuid.uuid4(),
                    user_id,
                    result_id,
                    document_result.get("document_type") or "CCCD",
                    identity_hash,
                    encrypt_document_payload({"identity_number": identity_number}),
                    fields.get("full_name"),
                    fields.get("date_of_birth"),
                    fields.get("sex"),
                    fields.get("nationality"),
                    fields.get("issue_date"),
                    fields.get("expiry_date"),
                    now,
                ),
            )
        conn.commit()
    return not already_verified, email_to, full_name


def _update_video_request(
    *,
    request_id: str,
    video_status: str,
    video_result: dict[str, Any] | None = None,
    face_similarity: float | None = None,
    face_decision: str | None = None,
    video_error_message: str | None = None,
    processed: bool = False,
) -> None:
    processed_at = datetime.now(timezone.utc) if processed else None
    with _require_psycopg().connect(_database_url()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE ekyc_sessions
                SET updated_at = NOW()
                WHERE request_id = %s
                """,
                (request_id,),
            )
            cur.execute(
                """
                UPDATE ekyc_video_results
                SET status = %s,
                    video_result = %s,
                    face_similarity = %s,
                    face_decision = %s,
                    error_message = %s,
                    model_version = %s,
                    started_at = COALESCE(started_at, NOW()),
                    completed_at = COALESCE(%s, completed_at)
                WHERE id = (
                    SELECT r.id
                    FROM ekyc_video_results r
                    JOIN ekyc_sessions s ON s.id = r.session_id
                    WHERE s.request_id = %s
                    ORDER BY r.created_at DESC
                    LIMIT 1
                )
                """,
                (
                    video_status,
                    Jsonb(video_result) if video_result is not None else None,
                    face_similarity,
                    face_decision,
                    video_error_message,
                    MODEL_VERSION,
                    processed_at,
                    request_id,
                ),
            )
        conn.commit()


def _resolve_image_path(image_path: str) -> Path:
    path = Path(image_path)
    if path.is_absolute():
        return path

    base_dir = Path(os.getenv("EKYC_WORKER_BASE_DIR", Path.cwd()))
    return base_dir / path


def _normalize_ocr_result(result: Any) -> dict[str, Any]:
    parsed_fields = result.parsed_fields.model_dump() if result.parsed_fields else {}
    normalized = {
        "full_name": parsed_fields.get("full_name"),
        "date_of_birth": parsed_fields.get("date_of_birth"),
        "sex": parsed_fields.get("sex"),
        "nationality": parsed_fields.get("nationality"),
        "id_number": parsed_fields.get("id_number") or parsed_fields.get("passport_number"),
        "address": parsed_fields.get("place_of_residence")
        or parsed_fields.get("place_of_origin"),
        "place_of_origin": parsed_fields.get("place_of_origin"),
        "place_of_residence": parsed_fields.get("place_of_residence"),
        "issue_date": parsed_fields.get("issue_date"),
        "issue_place": parsed_fields.get("issue_place"),
        "expiry_date": parsed_fields.get("expiry_date"),
        "document_type": _public_document_type(result.document_type),
        "ocr_confidence": round(result.ocr_confidence, 4),
        "image_quality_score": round(result.image_quality_score, 4),
        "document_face_detected": result.document_face_detected,
        "record_id": result.record_id,
        "side": "both",
        "warnings": result.warnings,
    }
    return {key: value for key, value in normalized.items() if value is not None}


def _validated_status(ocr_result: dict[str, Any]) -> tuple[str, str | None]:
    if not ocr_result.get("id_number") and not ocr_result.get("full_name"):
        return (
            "MANUAL_REVIEW",
            "OCR chua trich xuat du so giay to hoac ho ten, can kiem tra thu cong.",
        )
    return "SUCCESS", None


def _extract_image_paths(payload: dict[str, Any]) -> tuple[Path, Path | None]:
    front_path = payload.get("front_image_path") or payload.get("image_path")
    back_path = payload.get("back_image_path")
    if not front_path:
        raise ValueError("Missing front_image_path in eKYC job payload")
    return _resolve_image_path(str(front_path)), (
        _resolve_image_path(str(back_path)) if back_path else None
    )


def _extract_video_paths(payload: dict[str, Any]) -> tuple[Path, Path]:
    front_path = payload.get("front_image_path") or payload.get("image_path")
    video_path = payload.get("video_path")
    if not front_path:
        raise ValueError("Missing front_image_path in eKYC video job payload")
    if not video_path:
        raise ValueError("Missing video_path in eKYC video job payload")
    return _resolve_image_path(str(front_path)), _resolve_image_path(str(video_path))


def _extract_unified_paths(payload: dict[str, Any]) -> tuple[Path, Path | None, Path]:
    front_image_path, back_image_path = _extract_image_paths(payload)
    liveness_path = payload.get("liveness_path") or payload.get("video_path")
    if not liveness_path:
        raise ValueError("Missing liveness_path in unified eKYC job payload")
    return (
        front_image_path,
        back_image_path,
        _resolve_image_path(str(liveness_path)),
    )


def _face_decision_from_similarity(similarity: float | None) -> str:
    if similarity is None:
        return "not_match"
    match_threshold = float(os.getenv("EKYC_FACE_MATCH_THRESHOLD", "0.45"))
    consider_threshold = float(os.getenv("EKYC_FACE_CONSIDER_THRESHOLD", "0.30"))
    if similarity >= match_threshold:
        return "match"
    if similarity >= consider_threshold:
        return "consider"
    return "not_match"


def _overall_ekyc_decision(
    *,
    document_result: Any,
    video_result: Any,
) -> str:
    if (
        not document_result.document_face_detected
        or video_result.decision is None
        or video_result.decision == "failed"
    ):
        return "failed"
    if not document_result.document_face_confident or video_result.decision == "consider":
        return "consider"
    return "match"


def _status_from_decision(decision: str) -> str:
    if decision == "match":
        return "SUCCESS"
    if decision == "consider":
        return "MANUAL_REVIEW"
    return "FAILED"


def _voice_result_json(
    liveness_path: Path,
    *,
    expected_text: str | None,
    voice_verification: Any | None,
) -> dict[str, Any]:
    if voice_verification is not None:
        return voice_verification.model_dump(mode="json")

    return {
        "provided": bool(expected_text),
        "expected_text": expected_text,
        "source": "liveness_audio",
        "file_name": liveness_path.name,
        "size_bytes": liveness_path.stat().st_size,
    }


def _build_unified_result_payload(
    *,
    decision: str,
    similarity: float | None,
    score: float,
    confidence: float,
    document_payload: dict[str, Any],
    video_payload: dict[str, Any],
    voice_payload: dict[str, Any],
    warnings: list[str],
) -> dict[str, Any]:
    return {
        "success": decision == "match",
        "decision": decision,
        "similarity": similarity,
        "score": score,
        "confidence": confidence,
        "front_document": document_payload,
        "video": video_payload,
        "voice": voice_payload,
        "warnings": warnings,
    }


def _process_ocr_job(payload: dict[str, Any]) -> None:
    request_id = str(payload["request_id"])
    job_type = payload.get("job_type")
    document_type_hint = _ai_document_type(
        payload.get("document_type_hint") or payload.get("document_type")
    )

    front_image_path, back_image_path = _extract_image_paths(payload)
    logger.info("Worker started job request_id=%s job_type=%s", request_id, job_type)
    _update_request(request_id=request_id, status="PROCESSING")

    pipeline = DocumentPipeline(PipelineConfig())
    result = pipeline.analyze_two_sides(
        front_image_path,
        back_image_path,
        document_type_hint=document_type_hint,
        include_face_crop=False,
        save_private_record=True,
    )
    ocr_result = _normalize_ocr_result(result)
    next_status, review_message = _validated_status(ocr_result)
    masked_ocr_result = mask_document_payload(ocr_result)

    _update_request(
        request_id=request_id,
        status=next_status,
        ocr_result=masked_ocr_result,
        error_message=review_message,
        processed=True,
    )
    logger.info("OCR success request_id=%s status=%s", request_id, next_status)


def _process_video_job(payload: dict[str, Any]) -> None:
    request_id = str(payload["request_id"])
    front_image_path, video_path = _extract_video_paths(payload)
    logger.info("Worker started video job request_id=%s", request_id)
    _update_video_request(request_id=request_id, video_status="PROCESSING")

    pipeline = BiometricPipeline(PipelineConfig())
    result = pipeline.analyze_video(
        video_path.read_bytes(),
        front_image_path.read_bytes(),
    )
    video_result = result.model_dump(mode="json")
    similarity = result.matching.similarity if result.matching is not None else None
    face_decision = _face_decision_from_similarity(similarity)
    video_status = "SUCCESS" if face_decision == "match" else "FAILED"
    video_error_message = (
        None
        if face_decision == "match"
        else "Khuon mat trong video khong khop voi anh tren giay to. Vui long thu lai video khac."
    )

    _update_video_request(
        request_id=request_id,
        video_status=video_status,
        video_result=video_result,
        face_similarity=similarity,
        face_decision=face_decision,
        video_error_message=video_error_message,
        processed=True,
    )
    logger.info(
        "Video eKYC success request_id=%s decision=%s similarity=%s",
        request_id,
        face_decision,
        similarity,
    )


def _process_unified_job(payload: dict[str, Any]) -> None:
    request_id = str(payload["request_id"])
    document_type_hint = _ai_document_type(
        payload.get("document_type_hint") or payload.get("document_type")
    )
    front_image_path, back_image_path, liveness_path = _extract_unified_paths(payload)
    expected_text = str(payload.get("expected_text") or "").strip() or None
    logger.info("Worker started unified eKYC job request_id=%s", request_id)
    _update_unified_request(request_id=request_id, status="PROCESSING")

    document_result = DocumentPipeline(PipelineConfig()).analyze_two_sides(
        front_image_path,
        back_image_path,
        document_type_hint=document_type_hint,
        include_face_crop=False,
        save_private_record=True,
    )
    video_result = BiometricPipeline(PipelineConfig()).analyze_video(
        liveness_path.read_bytes(),
        front_image_path.read_bytes(),
        expected_text=expected_text,
    )
    private_document_payload = document_result.to_full_json()
    encrypted_document_payload = encrypt_document_payload(private_document_payload)
    masked_document_payload = mask_document_payload(private_document_payload)
    video_payload = video_result.model_dump(mode="json")
    voice_payload = _voice_result_json(
        liveness_path,
        expected_text=expected_text,
        voice_verification=video_result.voice_verification,
    )
    similarity = video_result.matching.similarity if video_result.matching else None
    confidence_values = [
        document_result.ocr_confidence,
        document_result.image_quality_score,
        video_result.quality_score,
        video_result.passive_liveness.score,
    ]
    confidence = round(sum(confidence_values) / len(confidence_values), 4)
    score_values = [confidence]
    if similarity is not None:
        score_values.append(max(0.0, min(1.0, similarity)))
    score = round(sum(score_values) / len(score_values), 4)
    decision = _overall_ekyc_decision(
        document_result=document_result,
        video_result=video_result,
    )
    status = _status_from_decision(decision)
    warnings = [*document_result.warnings, *video_result.warnings]
    result = _build_unified_result_payload(
        decision=decision,
        similarity=similarity,
        score=score,
        confidence=confidence,
        document_payload=masked_document_payload,
        video_payload=video_payload,
        voice_payload=voice_payload,
        warnings=warnings,
    )
    config = PipelineConfig()
    if config.llm_admin_review_enabled and config.llm_admin_review_auto:
        reviewer = LLMAdminDecisionReviewer(config)
        if reviewer.is_ready():
            try:
                result["ai_admin_review"] = reviewer.review_unified_result(result).model_dump(
                    mode="json"
                )
            except Exception:
                logger.exception("LLM admin review failed request_id=%s", request_id)

    error_message = "; ".join(warnings)[:1024] if status != "SUCCESS" and warnings else None

    _update_unified_request(
        request_id=request_id,
        status=status,
        result=result,
        score=score,
        confidence=confidence,
        decision=decision,
        error_message=error_message,
        processed=True,
    )
    result_id, user_id = _save_ekyc_result(
        request_id=request_id,
        status=status,
        result=result,
        document_result=masked_document_payload,
        encrypted_document_result=encrypted_document_payload,
        liveness_result=video_payload,
        voice_result=voice_payload,
        score=score,
        confidence=confidence,
        decision=decision,
        error_message=error_message,
    )
    if status == "SUCCESS" and user_id is not None:
        should_notify, email_to, full_name = _save_verified_identity(
            user_id=user_id,
            result_id=result_id,
            document_result=private_document_payload,
        )
        if should_notify and email_to:
            try:
                _send_ekyc_verified_email(email_to=email_to, full_name=full_name)
            except Exception:
                logger.exception("Failed to send eKYC verification email to user_id=%s", user_id)
    logger.info(
        "Unified eKYC finished request_id=%s status=%s decision=%s score=%s raw_result=full document_result=full",
        request_id,
        status,
        decision,
        score,
    )


def _process_job(payload: dict[str, Any]) -> None:
    job_type = payload.get("job_type")
    if job_type == "EKYC_VERIFY_ALL":
        _process_unified_job(payload)
        return
    if job_type in {"OCR_ID_CARD_TWO_SIDES", "OCR_ID_CARD"}:
        _process_ocr_job(payload)
        return
    if job_type == "VIDEO_FACE_MATCH":
        _process_video_job(payload)
        return
    raise ValueError(f"Unsupported eKYC job type: {job_type}")


def _handle_failed_job(
    *,
    redis_client: redis.Redis,
    payload: dict[str, Any],
    exc: Exception,
) -> None:
    request_id = str(payload.get("request_id", "unknown"))
    attempt = int(payload.get("attempt", 1))
    logger.exception(
        "eKYC job failed request_id=%s attempt=%s/%s",
        request_id,
        attempt,
        MAX_RETRIES,
    )

    if attempt < MAX_RETRIES and request_id != "unknown":
        payload["attempt"] = attempt + 1
        time.sleep(RETRY_DELAY_SECONDS)
        redis_client.rpush(QUEUE_NAME, json.dumps(payload, ensure_ascii=False))
        logger.info("Requeued eKYC job request_id=%s attempt=%s", request_id, attempt + 1)
        return

    if request_id != "unknown":
        if payload.get("job_type") == "EKYC_VERIFY_ALL":
            error_message = str(exc)[:1024]
            failure_result = {
                "success": False,
                "decision": "failed",
                "score": None,
                "confidence": None,
                "error_message": error_message,
                "video": {
                    "success": False,
                    "decision": "failed",
                    "error_message": error_message,
                },
                "warnings": [error_message] if error_message else [],
            }
            liveness_result = failure_result["video"]
            _update_unified_request(
                request_id=request_id,
                status="FAILED",
                result=failure_result,
                decision="failed",
                error_message=error_message,
                processed=True,
            )
            try:
                _save_ekyc_result(
                    request_id=request_id,
                    status="FAILED",
                    result=failure_result,
                    document_result={},
                    liveness_result=liveness_result,
                    voice_result={},
                    score=None,
                    confidence=None,
                    decision="failed",
                    error_message=error_message,
                )
            except Exception:
                logger.exception("Failed to persist failed eKYC result request_id=%s", request_id)
            logger.info("DB updated request_id=%s status=FAILED", request_id)
        elif payload.get("job_type") == "VIDEO_FACE_MATCH":
            _update_video_request(
                request_id=request_id,
                video_status="FAILED",
                video_error_message=str(exc)[:1024],
                processed=True,
            )
            logger.info("DB updated request_id=%s video_status=FAILED", request_id)
        else:
            _update_request(
                request_id=request_id,
                status="FAILED",
                error_message=str(exc)[:1024],
                processed=True,
            )
            logger.info("DB updated request_id=%s status=FAILED", request_id)


def run_worker() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    redis_module = _require_redis()
    redis_client = redis_module.from_url(REDIS_URL, decode_responses=True)
    logger.info("eKYC worker listening queue=%s", QUEUE_NAME)

    while True:
        try:
            item = redis_client.blpop(QUEUE_NAME, timeout=5)
        except redis_module.exceptions.TimeoutError:
            continue
        if item is None:
            continue

        _, raw_payload = item
        payload: dict[str, Any] = {}
        try:
            payload = json.loads(raw_payload)
            _process_job(payload)
        except Exception as exc:
            _handle_failed_job(redis_client=redis_client, payload=payload, exc=exc)


if __name__ == "__main__":
    run_worker()
