import hmac
import json
import logging
import random
import shutil
import uuid
from datetime import datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy import String, cast, func, or_
from sqlmodel import Session, SQLModel, col, delete, select

from app.api.deps import (
    CurrentUser,
    SessionDep,
    can_review_ekyc,
    get_current_ekyc_reviewer,
)
from app.core.config import settings
from app.models import (
    EkycDocumentType,
    EkycDocumentFieldsAdminUpdate,
    EkycFile,
    EkycFileType,
    EkycRequestAdminPublic,
    EkycRequestCreateResponse,
    EkycRequestPublic,
    EkycRequestsAdminPublic,
    EkycRequestStatus,
    EkycResult,
    EkycSession,
    EkycVideoStatus,
    EkycVoiceSession,
    EkycVoiceSessionStatus,
    Message,
    MyVerifiedIdentityPublic,
    User,
    VerifiedIdentity,
    get_datetime_utc,
)
from app.services.ekyc_admin_ai_review import request_admin_ai_review
from app.services.admin_settings import get_ekyc_processing_timeout_minutes
from app.services.audit_log import create_admin_audit_log
from app.services.ekyc_crypto import (
    decrypt_document_payload,
    encrypt_document_payload,
    mask_document_payload,
)
from app.services.ekyc_queue import (
    EkycQueueError,
    enqueue_ekyc_job,
)
from app.services.notifications import create_user_notification

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ekyc/requests", tags=["ekyc"])

ALLOWED_CONTENT_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
}
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png"}
ALLOWED_VIDEO_CONTENT_TYPES = {
    "video/mp4": ".mp4",
}
ALLOWED_VIDEO_EXTENSIONS = {".mp4"}
MIN_VIDEO_UPLOAD_SIZE_BYTES = 1024
ADMIN_FILE_KIND_TO_TYPE = {
    "front": EkycFileType.DOCUMENT_FRONT,
    "back": EkycFileType.DOCUMENT_BACK,
    "liveness": EkycFileType.LIVENESS_VIDEO,
}
VOICE_CHALLENGE_FALLBACKS = (
    "Tôi xác nhận đây là tài khoản của tôi",
    "Tôi đồng ý xác minh danh tính hôm nay",
    "Tôi đang đọc câu này để xác minh danh tính",
    "Khuôn mặt trong video là của tôi",
    "Tôi xác nhận đây là giọng nói của tôi",
)
VOICE_SESSION_TIMEOUT_SECONDS = 5 * 60
VOICE_SESSION_DIGIT_COUNT = 6
VOICE_SESSION_MAX_ATTEMPTS = 3
VOICE_DIGIT_WORDS = {
    "0": "khong",
    "1": "mot",
    "2": "hai",
    "3": "ba",
    "4": "bon",
    "5": "nam",
    "6": "sau",
    "7": "bay",
    "8": "tam",
    "9": "chin",
}
_SECURE_RANDOM = random.SystemRandom()


class EkycManualDecisionPayload(SQLModel):
    reason: str | None = None


class EkycVoiceSessionPublic(SQLModel):
    session_id: uuid.UUID
    status: EkycVoiceSessionStatus
    display_digits: list[str]
    display_text: str
    spoken_hint: str
    attempts: int
    max_attempts: int
    remaining_attempts: int
    expires_at: datetime
    expires_in_seconds: int


class EkycVoiceVerifyResponse(EkycVoiceSessionPublic):
    verified: bool
    can_continue: bool
    reset_required: bool
    decision: str | None = None
    warning: str | None = None
    verified_against_text: str | None = None
    verified_against_hint: str | None = None


RETRYABLE_STATUSES = {
    EkycRequestStatus.FAILED,
    EkycRequestStatus.MANUAL_REVIEW,
}


def _status_message(status_value: EkycRequestStatus) -> str:
    messages = {
        EkycRequestStatus.PENDING: "Your eKYC request has been received and is waiting for processing.",
        EkycRequestStatus.PROCESSING: "Your eKYC request is being processed by the AI pipeline.",
        EkycRequestStatus.SUCCESS: "Your identity verification has been completed successfully.",
        EkycRequestStatus.FAILED: "We could not complete identity verification from the submitted files.",
        EkycRequestStatus.MANUAL_REVIEW: "Your identity verification requires manual review.",
    }
    return messages[status_value]


def _as_aware_utc(value: Any) -> Any:
    if value is None or getattr(value, "tzinfo", None) is not None:
        return value
    return value.replace(tzinfo=get_datetime_utc().tzinfo)


def _voice_challenge_from_digits(
    digits: list[str],
) -> tuple[list[str], str, str, str]:
    spoken_words = [VOICE_DIGIT_WORDS[digit] for digit in digits]
    return digits, " ".join(digits), " ".join(spoken_words), " - ".join(spoken_words)


def _generate_digit_voice_challenge() -> tuple[list[str], str, str, str]:
    digits = [
        str(_SECURE_RANDOM.randint(0, 9))
        for _ in range(VOICE_SESSION_DIGIT_COUNT)
    ]
    return _voice_challenge_from_digits(digits)


def _refresh_voice_challenge(voice_session: EkycVoiceSession) -> None:
    previous_display_text = voice_session.display_text
    digits, display_text, expected_text, spoken_hint = _generate_digit_voice_challenge()
    for _ in range(5):
        if display_text != previous_display_text:
            break
        digits, display_text, expected_text, spoken_hint = _generate_digit_voice_challenge()
    if display_text == previous_display_text and digits:
        digits = [*digits]
        digits[-1] = str((int(digits[-1]) + 1) % 10)
        digits, display_text, expected_text, spoken_hint = _voice_challenge_from_digits(
            digits
        )
    voice_session.display_digits = digits
    voice_session.display_text = display_text
    voice_session.expected_text = expected_text
    voice_session.spoken_hint = spoken_hint
    voice_session.updated_at = get_datetime_utc()


def _voice_session_public(voice_session: EkycVoiceSession) -> EkycVoiceSessionPublic:
    now = get_datetime_utc()
    expires_at = _as_aware_utc(voice_session.expires_at)
    expires_in = max(0, int((expires_at - now).total_seconds())) if expires_at else 0
    return EkycVoiceSessionPublic(
        session_id=voice_session.id,
        status=voice_session.status,
        display_digits=list(voice_session.display_digits),
        display_text=voice_session.display_text,
        spoken_hint=voice_session.spoken_hint,
        attempts=voice_session.attempts,
        max_attempts=voice_session.max_attempts,
        remaining_attempts=max(0, voice_session.max_attempts - voice_session.attempts),
        expires_at=voice_session.expires_at,
        expires_in_seconds=expires_in,
    )


def _new_voice_session(*, current_user: User) -> EkycVoiceSession:
    digits, display_text, expected_text, spoken_hint = _generate_digit_voice_challenge()
    now = get_datetime_utc()
    return EkycVoiceSession(
        user_id=current_user.id,
        display_digits=digits,
        display_text=display_text,
        expected_text=expected_text,
        spoken_hint=spoken_hint,
        attempts=0,
        max_attempts=VOICE_SESSION_MAX_ATTEMPTS,
        expires_at=now + timedelta(seconds=VOICE_SESSION_TIMEOUT_SECONDS),
    )


def _active_pending_voice_session(
    *,
    db_session: Session,
    current_user: User,
) -> EkycVoiceSession | None:
    now = get_datetime_utc()
    statement = (
        select(EkycVoiceSession)
        .where(EkycVoiceSession.user_id == current_user.id)
        .where(EkycVoiceSession.status == EkycVoiceSessionStatus.PENDING)
        .order_by(EkycVoiceSession.created_at.desc())
    )
    for voice_session in db_session.exec(statement):
        expires_at = _as_aware_utc(voice_session.expires_at)
        if expires_at > now:
            return voice_session
        _mark_voice_session_expired(
            db_session=db_session,
            voice_session=voice_session,
        )
    return None


def _get_voice_session_or_404(
    *,
    db_session: Session,
    current_user: User,
    voice_session_id: uuid.UUID,
) -> EkycVoiceSession:
    statement = (
        select(EkycVoiceSession)
        .where(EkycVoiceSession.id == voice_session_id)
        .where(EkycVoiceSession.user_id == current_user.id)
    )
    voice_session = db_session.exec(statement).first()
    if voice_session is None:
        raise HTTPException(status_code=404, detail="Voice session not found")
    return voice_session


def _mark_voice_session_expired(
    *,
    db_session: Session,
    voice_session: EkycVoiceSession,
) -> None:
    voice_session.status = EkycVoiceSessionStatus.EXPIRED
    voice_session.updated_at = get_datetime_utc()
    db_session.add(voice_session)
    db_session.commit()
    db_session.refresh(voice_session)


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


async def _read_video_upload_bytes(
    upload: UploadFile,
    *,
    label: str,
    max_size_mb: int,
) -> bytes:
    _validate_video_metadata(upload)
    content = await upload.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{label} is empty.")
    if len(content) > max_size_mb * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"{label} exceeds the {max_size_mb}MB limit.",
        )
    return content


async def _verify_voice_with_ai(
    *,
    file_content: bytes,
    filename: str,
    content_type: str,
    expected_text: str,
) -> dict[str, Any]:
    ai_base_url = settings.EKYC_AI_SERVICE_URL.rstrip("/")
    timeout_seconds = max(5.0, min(settings.EKYC_AI_REQUEST_TIMEOUT_SECONDS, 90.0))
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(
                f"{ai_base_url}/api/v1/voice/verify",
                data={"expected_text": expected_text},
                files={
                    "file": (
                        filename or "liveness.mp4",
                        file_content,
                        content_type or "video/mp4",
                    )
                },
            )
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        logger.warning("AI voice service rejected verification", exc_info=True)
        detail = _httpx_error_detail(exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Voice verification service error: {detail}",
        ) from exc
    except httpx.HTTPError as exc:
        logger.warning("Could not verify voice with AI service", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Voice verification is temporarily unavailable.",
        ) from exc

    try:
        payload = response.json()
    except ValueError as exc:
        logger.warning("AI voice service returned a non-JSON response", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Voice verification returned an invalid response.",
        ) from exc
    if not isinstance(payload, dict):
        logger.warning("AI voice service returned an unexpected payload: %r", payload)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Voice verification returned an invalid response.",
        )
    return payload


def _httpx_error_detail(exc: httpx.HTTPStatusError) -> str:
    response = exc.response
    try:
        payload = response.json()
    except ValueError:
        text = (response.text or "").strip()
        return f"AI {response.status_code}: {text[:240] or response.reason_phrase}"
    detail = payload.get("detail") if isinstance(payload, dict) else None
    if isinstance(detail, str) and detail.strip():
        return f"AI {response.status_code}: {detail.strip()[:240]}"
    return f"AI {response.status_code}: {response.reason_phrase}"


def _voice_ai_decision(payload: dict[str, Any]) -> str:
    decision = str(
        payload.get("voice_decision")
        or payload.get("decision")
        or ""
    ).lower()
    if payload.get("voice_passed") is True or payload.get("success") is True:
        return "match"
    return decision or "failed"


def _voice_retry_response(
    *,
    db_session: Session,
    voice_session: EkycVoiceSession,
    decision: str,
    warning: str,
) -> EkycVoiceVerifyResponse:
    verified_against_text = voice_session.display_text
    verified_against_hint = voice_session.spoken_hint
    voice_session.attempts += 1
    reset_required = voice_session.attempts >= voice_session.max_attempts
    if reset_required:
        voice_session.status = EkycVoiceSessionStatus.FAILED
    else:
        _refresh_voice_challenge(voice_session)
    db_session.add(voice_session)
    db_session.commit()
    db_session.refresh(voice_session)
    public_data = _voice_session_public(voice_session).model_dump()
    return EkycVoiceVerifyResponse(
        **public_data,
        verified=False,
        can_continue=False,
        reset_required=reset_required,
        decision=decision,
        warning=warning,
        verified_against_text=verified_against_text,
        verified_against_hint=verified_against_hint,
    )


def _submission_voice_session_or_400(
    *,
    db_session: Session,
    current_user: User,
    voice_session_id: uuid.UUID,
) -> EkycVoiceSession:
    voice_session = _get_voice_session_or_404(
        db_session=db_session,
        current_user=current_user,
        voice_session_id=voice_session_id,
    )
    if voice_session.status == EkycVoiceSessionStatus.PENDING:
        expires_at = _as_aware_utc(voice_session.expires_at)
        if expires_at <= get_datetime_utc():
            _mark_voice_session_expired(
                db_session=db_session,
                voice_session=voice_session,
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The voice challenge expired. Please redo Step 2.",
            )
        return voice_session
    if voice_session.status != EkycVoiceSessionStatus.PASSED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please redo Step 2 before submitting.",
        )
    if voice_session.verified_at is None or (
        _as_aware_utc(voice_session.verified_at)
        > _as_aware_utc(voice_session.expires_at)
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The passed voice session is no longer valid. Please redo Step 2.",
        )
    return voice_session


async def _fetch_voice_challenge_from_ai() -> dict[str, str] | None:
    ai_base_url = settings.EKYC_AI_SERVICE_URL.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(f"{ai_base_url}/api/v1/voice/challenge")
            response.raise_for_status()
    except httpx.HTTPError:
        logger.warning("Could not fetch voice challenge from AI service", exc_info=True)
        return None

    payload = response.json()
    expected_text = str(payload.get("expected_text") or "").strip()
    if not expected_text:
        return None
    instruction = str(
        payload.get("instruction")
        or "Please read the phrase aloud while recording your face video."
    )
    return {
        "expected_text": expected_text,
        "instruction": instruction,
    }


def _ai_document_type(document_type: EkycDocumentType) -> str:
    if document_type == EkycDocumentType.HOCHIEU:
        return "PASSPORT"
    return document_type.value


def _get_session_or_404(
    *,
    db_session: Session,
    current_user: User,
    request_id: uuid.UUID,
) -> EkycSession:
    statement = select(EkycSession).where(EkycSession.request_id == request_id)
    ekyc_session = db_session.exec(statement).first()
    if not ekyc_session:
        raise HTTPException(status_code=404, detail="eKYC request not found")
    if (
        not can_review_ekyc(current_user)
        and ekyc_session.user_id is not None
        and ekyc_session.user_id != current_user.id
    ):
        raise HTTPException(status_code=403, detail="Not enough permissions")
    return ekyc_session


def _validate_upload_metadata(file: UploadFile, *, label: str) -> str:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{label} must be a JPG, JPEG, or PNG file.",
        )

    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{label} must use image/jpeg or image/png content type.",
        )

    return ALLOWED_CONTENT_TYPES[file.content_type]


def _validate_video_metadata(file: UploadFile) -> str:
    suffix = Path(file.filename or "").suffix.lower()
    content_type = (file.content_type or "").split(";", 1)[0].strip().lower()
    if suffix not in ALLOWED_VIDEO_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The face verification video must be an MP4 file.",
        )

    if content_type in ALLOWED_VIDEO_CONTENT_TYPES:
        return ALLOWED_VIDEO_CONTENT_TYPES[content_type]

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="The face verification video must use video/mp4 content type.",
    )


def _latest_by_created_at(items: list[Any]) -> Any | None:
    if not items:
        return None
    return max(items, key=lambda item: item.created_at or get_datetime_utc())


def _ekyc_file(
    ekyc_session: EkycSession,
    file_type: EkycFileType,
) -> EkycFile | None:
    for ekyc_file in ekyc_session.files:
        if ekyc_file.file_type == file_type:
            return ekyc_file
    return None


def _front_image_path(ekyc_session: EkycSession) -> str | None:
    ekyc_file = _ekyc_file(ekyc_session, EkycFileType.DOCUMENT_FRONT)
    return ekyc_file.file_path if ekyc_file else None


def _back_image_path(ekyc_session: EkycSession) -> str | None:
    ekyc_file = _ekyc_file(ekyc_session, EkycFileType.DOCUMENT_BACK)
    return ekyc_file.file_path if ekyc_file else None


def _liveness_path(ekyc_session: EkycSession) -> str | None:
    ekyc_file = _ekyc_file(ekyc_session, EkycFileType.LIVENESS_VIDEO)
    return ekyc_file.file_path if ekyc_file else None


def _session_upload_directories(ekyc_session: EkycSession) -> set[Path]:
    upload_root = Path(settings.UPLOAD_DIR).resolve()
    directories: set[Path] = set()
    for ekyc_file in ekyc_session.files:
        file_path = Path(ekyc_file.file_path).resolve()
        parent = file_path.parent
        if parent == upload_root:
            continue
        try:
            parent.relative_to(upload_root)
        except ValueError:
            continue
        directories.add(parent)
    return directories


def _latest_result(ekyc_session: EkycSession) -> EkycResult | None:
    return _latest_by_created_at(ekyc_session.results)


def _latest_verified_identity(
    *,
    db_session: Session,
    user_id: uuid.UUID,
) -> VerifiedIdentity | None:
    statement = (
        select(VerifiedIdentity)
        .join(EkycResult, VerifiedIdentity.ekyc_result_id == EkycResult.id)
        .where(VerifiedIdentity.user_id == user_id)
        .where(col(VerifiedIdentity.revoked_at).is_(None))
        .order_by(VerifiedIdentity.verified_at.desc())  # type: ignore[union-attr]
    )
    return db_session.exec(statement).first()


def _identity_number_hash(identity_number: str) -> str:
    key = settings.EKYC_IDENTITY_HASH_KEY or settings.SECRET_KEY
    normalized = "".join(identity_number.split()).upper()
    return hmac.new(
        key.encode("utf-8"),
        normalized.encode("utf-8"),
        sha256,
    ).hexdigest()


def _document_fields(document_result: dict[str, Any] | None) -> dict[str, Any]:
    if not document_result:
        return {}
    for key in ("admin_corrected_fields", "document_confirmed_fields", "confirmed_fields"):
        fields = document_result.get(key)
        if isinstance(fields, dict):
            return fields
    parsed_fields = document_result.get("parsed_fields")
    return parsed_fields if isinstance(parsed_fields, dict) else document_result


def _confirmed_document_fields(
    ekyc_session: EkycSession,
    document_result: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    sources = (
        ekyc_session.result if isinstance(ekyc_session.result, dict) else None,
        document_result,
    )
    for source in sources:
        if not source:
            continue
        for key in ("admin_corrected_fields", "document_confirmed_fields", "confirmed_fields"):
            fields = source.get(key)
            if isinstance(fields, dict):
                return fields
    return None


def _confirmed_document_fields_from_result(
    result: EkycResult,
) -> dict[str, Any] | None:
    for source in (
        result.document_result if isinstance(result.document_result, dict) else None,
        result.raw_result if isinstance(result.raw_result, dict) else None,
    ):
        if not source:
            continue
        for key in ("admin_corrected_fields", "document_confirmed_fields", "confirmed_fields"):
            fields = source.get(key)
            if isinstance(fields, dict):
                return fields
    return None


def _document_confirmed_at(ekyc_session: EkycSession) -> datetime | None:
    source = ekyc_session.result if isinstance(ekyc_session.result, dict) else None
    if not source:
        return None
    raw_value = source.get("document_confirmed_at")
    if isinstance(raw_value, datetime):
        return raw_value
    if isinstance(raw_value, str) and raw_value.strip():
        try:
            return datetime.fromisoformat(raw_value)
        except ValueError:
            return None
    return None


def _with_confirmed_document_fields(
    ekyc_session: EkycSession,
    document_result: dict[str, Any] | None,
) -> dict[str, Any]:
    payload = dict(document_result) if isinstance(document_result, dict) else {}
    fields = _confirmed_document_fields(ekyc_session, payload)
    if not fields:
        return payload

    payload["admin_corrected_fields"] = fields
    payload["document_confirmed_fields"] = fields
    parsed_fields = payload.get("parsed_fields")
    if isinstance(parsed_fields, dict):
        payload["parsed_fields"] = {**parsed_fields, **fields}
    else:
        payload.update(fields)
    return payload


def _mask_identity_number(identity_number: str | None) -> str | None:
    value = (identity_number or "").strip()
    if not value:
        return None
    visible_digits = 4
    if len(value) <= visible_digits:
        return "*" * len(value)
    return f"{'*' * (len(value) - visible_digits)}{value[-visible_digits:]}"


def _identity_number_from_result(result: EkycResult | None) -> str | None:
    if result is None:
        return None

    document_result = decrypt_document_payload(result.encrypted_document_result)
    if not document_result:
        document_result = _private_record_document_payload(result) or result.document_result
        confirmed_fields = _confirmed_document_fields_from_result(result)
        if confirmed_fields:
            document_result = dict(document_result) if isinstance(document_result, dict) else {}
            document_result["admin_corrected_fields"] = confirmed_fields
            document_result["document_confirmed_fields"] = confirmed_fields
    fields = _document_fields(document_result)
    identity_number = str(
        fields.get("id_number") or fields.get("passport_number") or ""
    ).strip()
    return identity_number or None


def _identity_number_from_verified_identity(
    verified_identity: VerifiedIdentity,
    *,
    reveal: bool = False,
) -> str | None:
    encrypted_identity = decrypt_document_payload(
        verified_identity.identity_number_encrypted
    )
    if encrypted_identity:
        identity_number = str(encrypted_identity.get("identity_number") or "").strip()
        if identity_number:
            return identity_number
    if reveal:
        return None
    return _identity_number_from_result(verified_identity.ekyc_result)


def _first_field_value(fields: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = fields.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _private_record_id_from_result(result: EkycResult) -> str | None:
    document_result = result.document_result if isinstance(result.document_result, dict) else {}
    record_id = document_result.get("record_id")
    if not record_id:
        raw_result = result.raw_result if isinstance(result.raw_result, dict) else {}
        front_document = raw_result.get("front_document")
        if isinstance(front_document, dict):
            record_id = front_document.get("record_id")
    if not record_id:
        return None

    record_id_text = str(record_id).strip()
    try:
        uuid.UUID(record_id_text)
    except ValueError:
        return None
    return record_id_text


def _read_private_record_payload(result: EkycResult) -> dict[str, Any] | None:
    storage_dir = settings.EKYC_PRIVATE_STORAGE_DIR
    if not storage_dir:
        return None

    record_id = _private_record_id_from_result(result)
    if not record_id:
        return None

    record_path = Path(storage_dir) / "records" / f"{record_id}.json"
    try:
        payload = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Could not read private eKYC record %s", record_id)
        return None

    return payload if isinstance(payload, dict) else None


def _private_fields_from_record_payload(payload: dict[str, Any]) -> dict[str, Any]:
    fields = payload.get("fields")
    if not isinstance(fields, dict):
        nested_payload = payload.get("payload")
        nested_fields = (
            nested_payload.get("fields") if isinstance(nested_payload, dict) else None
        )
        fields = nested_fields if isinstance(nested_fields, dict) else None
    if not isinstance(fields, dict):
        return {}

    document_type = str(payload.get("document_type") or "").upper()
    document_number = fields.get("document_number")
    id_number = None if document_type == "PASSPORT" else document_number
    passport_number = document_number if document_type == "PASSPORT" else fields.get(
        "passport_number"
    )
    return {
        "id_number": id_number,
        "passport_number": passport_number,
        "full_name": fields.get("full_name"),
        "date_of_birth": fields.get("date_of_birth"),
        "place_of_origin": fields.get("place_of_origin"),
        "place_of_residence": fields.get("place_of_residence"),
        "issue_date": fields.get("issue_date"),
        "issue_place": fields.get("issue_place"),
        "expiry_date": fields.get("expiry_date"),
    }


def _private_record_document_payload(result: EkycResult) -> dict[str, Any] | None:
    payload = _read_private_record_payload(result)
    if not payload:
        return None

    nested_payload = payload.get("payload")
    if isinstance(nested_payload, dict) and "parsed_fields" in nested_payload:
        return nested_payload

    fields = _private_fields_from_record_payload(payload)
    if not fields:
        return None

    document_result = (
        dict(result.document_result) if isinstance(result.document_result, dict) else {}
    )
    parsed_fields = document_result.get("parsed_fields")
    parsed_payload = dict(parsed_fields) if isinstance(parsed_fields, dict) else {}
    cleaned_fields = {key: value for key, value in fields.items() if value}
    document_result["parsed_fields"] = {**parsed_payload, **cleaned_fields}
    document_result.update(cleaned_fields)
    document_result.setdefault("record_id", payload.get("record_id"))
    return document_result


def _private_record_document_fields(result: EkycResult) -> dict[str, Any]:
    document_payload = _private_record_document_payload(result)
    if document_payload:
        return _document_fields(document_payload)

    payload = _read_private_record_payload(result)
    if not payload:
        return {}
    fields = payload.get("fields")
    if not isinstance(fields, dict):
        nested_payload = payload.get("payload")
        fields = nested_payload.get("fields") if isinstance(nested_payload, dict) else None
    if not isinstance(fields, dict):
        return {}

    return {
        "id_number": fields.get("document_number"),
        "passport_number": fields.get("passport_number"),
        "full_name": fields.get("full_name"),
        "date_of_birth": fields.get("date_of_birth"),
        "place_of_origin": fields.get("place_of_origin"),
        "place_of_residence": fields.get("place_of_residence"),
        "issue_date": fields.get("issue_date"),
        "issue_place": fields.get("issue_place"),
        "expiry_date": fields.get("expiry_date"),
    }


def _verified_identity_document_fields(
    verified_identity: VerifiedIdentity,
    *,
    reveal: bool = False,
) -> dict[str, Any]:
    result = verified_identity.ekyc_result
    if result is None:
        return {}

    decrypted_result = decrypt_document_payload(result.encrypted_document_result)
    if decrypted_result:
        return _document_fields(decrypted_result)
    if reveal:
        return _private_record_document_fields(result)
    return _document_fields(result.document_result)


def _document_result_for_identity(
    ekyc_session: EkycSession,
    result: EkycResult | None,
) -> dict[str, Any]:
    document_result: dict[str, Any] | None = None
    if result:
        decrypted_result = decrypt_document_payload(result.encrypted_document_result)
        if decrypted_result:
            return decrypted_result
        private_result = _private_record_document_payload(result)
        if private_result:
            return private_result
        if result.document_result:
            document_result = result.document_result
    if document_result is None and ekyc_session.result:
        document_result = ekyc_session.result
    return _with_confirmed_document_fields(ekyc_session, document_result)


def _admin_document_result(result: EkycResult | None) -> dict[str, Any] | None:
    if result is None:
        return None

    decrypted_result = decrypt_document_payload(result.encrypted_document_result)
    if decrypted_result:
        return decrypted_result

    private_result = _private_record_document_payload(result)
    if private_result:
        return private_result

    return result.document_result if isinstance(result.document_result, dict) else None


def _active_verified_identity_by_hash(
    *,
    db_session: Session,
    identity_number_hash: str,
    exclude_result_id: uuid.UUID | None = None,
) -> VerifiedIdentity | None:
    statement = (
        select(VerifiedIdentity)
        .where(VerifiedIdentity.identity_number_hash == identity_number_hash)
        .where(col(VerifiedIdentity.revoked_at).is_(None))
        .order_by(VerifiedIdentity.verified_at.desc())  # type: ignore[union-attr]
    )
    if exclude_result_id is not None:
        statement = statement.where(
            or_(
                col(VerifiedIdentity.ekyc_result_id).is_(None),
                VerifiedIdentity.ekyc_result_id != exclude_result_id,
            )
        )
    return db_session.exec(statement).first()


def _duplicate_identity_warning(
    *,
    db_session: Session,
    ekyc_session: EkycSession,
    result: EkycResult | None,
) -> str | None:
    document_result = _document_result_for_identity(ekyc_session, result)
    fields = _document_fields(document_result)
    identity_number = str(
        fields.get("id_number") or fields.get("passport_number") or ""
    ).strip()
    if not identity_number:
        return None

    duplicate = _active_verified_identity_by_hash(
        db_session=db_session,
        identity_number_hash=_identity_number_hash(identity_number),
        exclude_result_id=result.id if result is not None else None,
    )
    if duplicate is None:
        return None

    duplicate_owner = db_session.get(User, duplicate.user_id)
    owner_label = (
        duplicate_owner.email
        if duplicate_owner and duplicate_owner.email
        else str(duplicate.user_id)
    )
    verified_at = duplicate.verified_at.isoformat() if duplicate.verified_at else "unknown time"
    return (
        "Duplicate identity number detected. This document number is already "
        f"active on account {owner_label} since {verified_at}."
    )


def _upsert_manual_result(
    *,
    db_session: Session,
    current_user: User,
    ekyc_session: EkycSession,
    status_value: EkycRequestStatus,
    decision: str,
    reason: str | None,
) -> EkycResult:
    now = get_datetime_utc()
    result = _latest_result(ekyc_session)
    manual_note = {
        "action": "approve" if status_value == EkycRequestStatus.SUCCESS else "reject",
        "reason": reason,
        "reviewed_at": now.isoformat(),
        "reviewer_id": str(current_user.id),
        "reviewer_email": current_user.email,
    }

    if result is None:
        result = EkycResult(
            session_id=ekyc_session.id,
            user_id=ekyc_session.user_id,
            status=status_value,
            decision=decision,
            document_result=ekyc_session.result,
            raw_result={"manual_review": manual_note},
            error_message=reason if status_value == EkycRequestStatus.FAILED else None,
            model_version=ekyc_session.model_version,
            completed_at=now,
        )
    else:
        raw_result = result.raw_result if isinstance(result.raw_result, dict) else {}
        result.status = status_value
        result.decision = decision
        result.raw_result = {**raw_result, "manual_review": manual_note}
        result.error_message = reason if status_value == EkycRequestStatus.FAILED else None
        result.completed_at = now

    db_session.add(result)
    db_session.commit()
    db_session.refresh(result)
    return result


def _save_manual_verified_identity(
    *,
    db_session: Session,
    ekyc_session: EkycSession,
    result: EkycResult,
) -> None:
    if ekyc_session.user_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot approve an eKYC request without an owner user.",
        )

    document_result = _document_result_for_identity(ekyc_session, result)
    fields = _document_fields(document_result)
    identity_number = str(
        fields.get("id_number") or fields.get("passport_number") or ""
    ).strip()
    if not identity_number:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot approve because the document number is missing from OCR data.",
        )

    duplicate = _active_verified_identity_by_hash(
        db_session=db_session,
        identity_number_hash=_identity_number_hash(identity_number),
        exclude_result_id=result.id,
    )
    if duplicate is not None:
        duplicate_owner = db_session.get(User, duplicate.user_id)
        owner_label = (
            duplicate_owner.email
            if duplicate_owner and duplicate_owner.email
            else str(duplicate.user_id)
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Cannot approve because this identity number is already verified "
                f"for account {owner_label}."
            ),
        )

    now = get_datetime_utc()
    statement = select(VerifiedIdentity).where(
        VerifiedIdentity.ekyc_result_id == result.id
    )
    verified_identity = db_session.exec(statement).first()
    if verified_identity is None:
        verified_identity = VerifiedIdentity(
            user_id=ekyc_session.user_id,
            ekyc_result_id=result.id,
            identity_number_hash=_identity_number_hash(identity_number),
        )

    verified_identity.user_id = ekyc_session.user_id
    verified_identity.ekyc_result_id = result.id
    verified_identity.document_type = ekyc_session.document_type
    verified_identity.identity_number_hash = _identity_number_hash(identity_number)
    verified_identity.identity_number_encrypted = None
    verified_identity.full_name = fields.get("full_name")
    verified_identity.birth_date = fields.get("date_of_birth") or fields.get("birth_year")
    verified_identity.gender = fields.get("sex") or fields.get("gender")
    verified_identity.nationality = fields.get("nationality")
    verified_identity.issued_date = fields.get("issue_date")
    verified_identity.expired_date = fields.get("expiry_date") or fields.get("expired_date")
    verified_identity.verified_at = now
    verified_identity.revoked_at = None
    verified_identity.updated_at = now

    db_session.add(verified_identity)
    try:
        db_session.commit()
    except IntegrityError as exc:
        db_session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot approve because this identity number is already verified for another active account.",
        ) from exc


def _revoke_verified_identity_for_result(
    *,
    db_session: Session,
    result_id: uuid.UUID,
) -> None:
    statement = select(VerifiedIdentity).where(
        VerifiedIdentity.ekyc_result_id == result_id
    )
    verified_identity = db_session.exec(statement).first()
    if verified_identity is None:
        return

    now = get_datetime_utc()
    verified_identity.revoked_at = now
    verified_identity.updated_at = now
    db_session.add(verified_identity)
    db_session.commit()


def _revoke_verified_identities_for_results(
    *,
    db_session: Session,
    result_ids: list[uuid.UUID],
) -> None:
    if not result_ids:
        return

    statement = (
        select(VerifiedIdentity)
        .where(col(VerifiedIdentity.ekyc_result_id).in_(result_ids))
        .where(col(VerifiedIdentity.revoked_at).is_(None))
    )
    verified_identities = db_session.exec(statement).all()
    if not verified_identities:
        return

    now = get_datetime_utc()
    for verified_identity in verified_identities:
        verified_identity.revoked_at = now
        verified_identity.updated_at = now
        db_session.add(verified_identity)


def _has_document_number(document_result: dict[str, Any]) -> bool:
    fields = _document_fields(document_result)
    return bool(str(fields.get("id_number") or fields.get("passport_number") or "").strip())


def _expected_text_from_result(result: EkycResult | None) -> str | None:
    if not result:
        return None

    voice_result = result.voice_result if isinstance(result.voice_result, dict) else {}
    expected_text = str(voice_result.get("expected_text") or "").strip()
    if expected_text:
        return expected_text

    raw_result = result.raw_result if isinstance(result.raw_result, dict) else {}
    raw_voice = raw_result.get("voice")
    if isinstance(raw_voice, dict):
        expected_text = str(raw_voice.get("expected_text") or "").strip()
        if expected_text:
            return expected_text
    return None


def _is_processing_stale(
    ekyc_session: EkycSession,
    processing_timeout_minutes: int,
) -> bool:
    if ekyc_session.status != EkycRequestStatus.PROCESSING:
        return False
    reference_time = ekyc_session.updated_at or ekyc_session.created_at
    if reference_time is None:
        return True
    now = get_datetime_utc()
    if reference_time.tzinfo is None:
        reference_time = reference_time.replace(tzinfo=now.tzinfo)
    return now - reference_time > timedelta(minutes=processing_timeout_minutes)


def _retry_payload_or_400(ekyc_session: EkycSession) -> dict[str, Any]:
    front_image_path = _front_image_path(ekyc_session)
    back_image_path = _back_image_path(ekyc_session)
    liveness_path = _liveness_path(ekyc_session)
    missing_kinds = [
        label
        for label, file_path in (
            ("front image", front_image_path),
            ("back image", back_image_path),
            ("liveness video", liveness_path),
        )
        if not file_path or not Path(file_path).is_file()
    ]
    if missing_kinds:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot retry because missing file(s): {', '.join(missing_kinds)}.",
        )

    latest_result = _latest_result(ekyc_session)
    return {
        "request_id": str(ekyc_session.request_id),
        "image_path": str(front_image_path),
        "front_image_path": str(front_image_path),
        "back_image_path": str(back_image_path),
        "liveness_path": str(liveness_path),
        "expected_text": _expected_text_from_result(latest_result) or "",
        "document_type": ekyc_session.document_type.value,
        "document_type_hint": _ai_document_type(ekyc_session.document_type),
        "job_type": "EKYC_VERIFY_ALL",
        "retry": True,
    }


def _latest_user_session(
    *,
    db_session: Session,
    user_id: uuid.UUID,
) -> EkycSession | None:
    statement = (
        select(EkycSession)
        .where(EkycSession.user_id == user_id)
        .order_by(EkycSession.created_at.desc())  # type: ignore[union-attr]
    )
    return db_session.exec(statement).first()


async def _save_upload_file(
    file: UploadFile,
    destination: Path,
    *,
    label: str,
    max_size_mb: int,
) -> None:
    max_bytes = max_size_mb * 1024 * 1024
    bytes_written = 0

    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as output:
        while chunk := await file.read(1024 * 1024):
            bytes_written += len(chunk)
            if bytes_written > max_bytes:
                output.close()
                destination.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=(
                        f"{label} vuot qua gioi han {max_size_mb}MB."
                    ),
                )
            output.write(chunk)

    if bytes_written == 0:
        destination.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{label} rong.",
        )


def _request_public(ekyc_session: EkycSession) -> EkycRequestPublic:
    result = _latest_result(ekyc_session)
    raw_result = result.raw_result if result else ekyc_session.result
    document_result = result.document_result if result else None
    liveness_result = result.liveness_result if result else None
    voice_result = result.voice_result if result else None
    video_status = (
        EkycVideoStatus.SUCCESS
        if result and result.decision == "match"
        else EkycVideoStatus.FAILED
        if result and result.status == EkycRequestStatus.FAILED
        else EkycVideoStatus.PROCESSING
        if ekyc_session.status == EkycRequestStatus.PROCESSING
        else EkycVideoStatus.PENDING
        if ekyc_session.status == EkycRequestStatus.PENDING
        else EkycVideoStatus.NOT_STARTED
    )
    return EkycRequestPublic(
        request_id=ekyc_session.request_id,
        status=ekyc_session.status,
        document_type=ekyc_session.document_type,
        message=_status_message(ekyc_session.status),
        result=raw_result,
        score=result.score if result else ekyc_session.score,
        confidence=result.confidence if result else ekyc_session.confidence,
        decision=result.decision if result else ekyc_session.decision,
        ocr_result=document_result,
        document_confirmed_fields=_confirmed_document_fields(
            ekyc_session,
            document_result,
        ),
        document_confirmed_at=_document_confirmed_at(ekyc_session),
        video_status=video_status,
        video_result=liveness_result,
        voice_result=voice_result,
        face_similarity=raw_result.get("similarity") if raw_result else None,
        face_decision=result.decision if result else ekyc_session.decision,
        error_message=ekyc_session.error_message or (result.error_message if result else None),
        video_error_message=result.error_message
        if result and result.status == EkycRequestStatus.FAILED
        else None,
        model_version=ekyc_session.model_version or (result.model_version if result else None),
        created_at=ekyc_session.created_at,
        updated_at=ekyc_session.updated_at,
        processed_at=ekyc_session.processed_at or (result.completed_at if result else None),
        video_processed_at=result.completed_at if result else None,
    )


def _ai_admin_review_from_sources(
    result: EkycResult | None,
    ekyc_session: EkycSession,
) -> dict[str, Any] | None:
    for source in (
        result.raw_result if result and isinstance(result.raw_result, dict) else None,
        ekyc_session.result if isinstance(ekyc_session.result, dict) else None,
    ):
        if source and isinstance(source.get("ai_admin_review"), dict):
            return source["ai_admin_review"]
    return None


def _unified_result_for_admin_review(
    ekyc_session: EkycSession,
    result: EkycResult | None,
) -> dict[str, Any]:
    raw = result.raw_result if result and isinstance(result.raw_result, dict) else None
    if raw:
        payload = dict(raw)
        payload.setdefault("request_id", str(ekyc_session.request_id))
        return payload
    if isinstance(ekyc_session.result, dict):
        payload = dict(ekyc_session.result)
        payload.setdefault("request_id", str(ekyc_session.request_id))
        return payload
    return {
        "request_id": str(ekyc_session.request_id),
        "decision": result.decision if result else ekyc_session.decision,
        "score": result.score if result else ekyc_session.score,
        "confidence": result.confidence if result else ekyc_session.confidence,
        "front_document": result.document_result if result else None,
        "video": result.liveness_result if result else None,
        "voice": result.voice_result if result else None,
    }


def _request_admin_public(
    db_session: Session,
    ekyc_session: EkycSession,
) -> EkycRequestAdminPublic:
    public_data = _request_public(ekyc_session).model_dump()
    result = _latest_result(ekyc_session)
    duplicate_warning = _duplicate_identity_warning(
        db_session=db_session,
        ekyc_session=ekyc_session,
        result=result,
    )
    admin_document_result = _admin_document_result(result)
    admin_confirmed_fields = (
        _document_fields(admin_document_result)
        if admin_document_result
        else public_data.get("document_confirmed_fields")
    )
    front_image_path = _front_image_path(ekyc_session)
    back_image_path = _back_image_path(ekyc_session)
    liveness_path = _liveness_path(ekyc_session)
    for key in (
        "ocr_result",
        "video_result",
        "voice_result",
        "error_message",
        "video_error_message",
        "document_confirmed_fields",
        "document_confirmed_at",
    ):
        public_data.pop(key, None)
    return EkycRequestAdminPublic(
        **public_data,
        id=ekyc_session.id,
        user_id=ekyc_session.user_id,
        owner_email=ekyc_session.owner.email if ekyc_session.owner else None,
        owner_full_name=ekyc_session.owner.full_name if ekyc_session.owner else None,
        duplicate_identity_detected=duplicate_warning is not None,
        duplicate_identity_warning=duplicate_warning,
        image_path=front_image_path,
        front_image_path=front_image_path,
        back_image_path=back_image_path,
        liveness_path=liveness_path,
        voice_path=None,
        video_path=liveness_path,
        ocr_result=admin_document_result,
        document_confirmed_fields=admin_confirmed_fields,
        document_confirmed_at=_document_confirmed_at(ekyc_session),
        video_result=result.liveness_result if result else None,
        voice_result=result.voice_result if result else None,
        ai_admin_review=_ai_admin_review_from_sources(result, ekyc_session),
        error_message=result.error_message if result else ekyc_session.error_message,
        video_error_message=result.error_message if result else None,
    )


def _clean_admin_document_fields(
    payload: EkycDocumentFieldsAdminUpdate,
    existing_fields: dict[str, Any],
) -> dict[str, Any]:
    updated_fields = dict(existing_fields)
    for key, value in payload.model_dump(exclude_unset=True).items():
        if value is None:
            updated_fields.pop(key, None)
            continue
        if isinstance(value, str):
            text = value.strip()
            if text:
                updated_fields[key] = text
            else:
                updated_fields.pop(key, None)
            continue
        updated_fields[key] = value
    return updated_fields


def _store_admin_document_fields(
    *,
    ekyc_session: EkycSession,
    latest_result: EkycResult | None,
    private_document_result: dict[str, Any],
    fields: dict[str, Any],
    confirmed_at: datetime,
) -> None:
    private_document_payload = dict(private_document_result)
    parsed_fields = private_document_payload.get("parsed_fields")
    if isinstance(parsed_fields, dict):
        private_document_payload["parsed_fields"] = {**parsed_fields, **fields}
    else:
        private_document_payload.update(fields)
    private_document_payload["admin_corrected_fields"] = fields
    private_document_payload["document_confirmed_fields"] = fields

    encrypted_document_payload = encrypt_document_payload(private_document_payload)
    if not encrypted_document_payload:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Cannot encrypt corrected document fields. Check eKYC PII key configuration.",
        )

    masked_document_payload = mask_document_payload(private_document_payload)
    masked_fields = _document_fields(masked_document_payload)

    session_result = ekyc_session.result if isinstance(ekyc_session.result, dict) else {}
    front_document = session_result.get("front_document")
    if isinstance(front_document, dict):
        session_result = {
            **session_result,
            "front_document": masked_document_payload,
        }
    ekyc_session.result = {
        **session_result,
        "admin_corrected_fields": masked_fields,
        "document_confirmed_fields": masked_fields,
        "document_confirmed_at": confirmed_at.isoformat(),
    }

    if latest_result is None:
        return

    latest_result.document_result = masked_document_payload
    latest_result.encrypted_document_result = encrypted_document_payload

    raw_result = (
        latest_result.raw_result if isinstance(latest_result.raw_result, dict) else {}
    )
    raw_front_document = raw_result.get("front_document")
    if isinstance(raw_front_document, dict):
        raw_result = {
            **raw_result,
            "front_document": masked_document_payload,
        }
    latest_result.raw_result = {
        **raw_result,
        "document_confirmed_fields": masked_fields,
        "document_confirmed_at": confirmed_at.isoformat(),
    }


@router.get(
    "",
    dependencies=[Depends(get_current_ekyc_reviewer)],
    response_model=EkycRequestsAdminPublic,
    include_in_schema=False,
)
@router.get(
    "/",
    dependencies=[Depends(get_current_ekyc_reviewer)],
    response_model=EkycRequestsAdminPublic,
)
def read_ekyc_requests(
    session: SessionDep,
    skip: int = 0,
    limit: int = 100,
    status: EkycRequestStatus | None = None,
    video_status: EkycVideoStatus | None = None,
    face_decision: str | None = None,
    q: str | None = None,
    sort: str = "latest",
) -> Any:
    statement = select(EkycSession).outerjoin(User).outerjoin(
        EkycResult,
        EkycResult.session_id == EkycSession.id,
    )
    count_statement = select(func.count()).select_from(EkycSession).outerjoin(User).outerjoin(
        EkycResult,
        EkycResult.session_id == EkycSession.id,
    )

    filters = []
    if status is not None:
        filters.append(EkycSession.status == status)
    if face_decision:
        filters.append(EkycResult.decision == face_decision)
    if video_status is not None:
        if video_status == EkycVideoStatus.SUCCESS:
            filters.append(EkycResult.decision == "match")
        elif video_status == EkycVideoStatus.FAILED:
            filters.append(EkycResult.status == EkycRequestStatus.FAILED)
        elif video_status == EkycVideoStatus.PROCESSING:
            filters.append(EkycSession.status == EkycRequestStatus.PROCESSING)
        elif video_status == EkycVideoStatus.PENDING:
            filters.append(EkycSession.status == EkycRequestStatus.PENDING)
        elif video_status == EkycVideoStatus.NOT_STARTED:
            filters.append(EkycResult.id.is_(None))

    search_query = (q or "").strip()
    if search_query:
        needle = f"%{search_query}%"
        filters.append(
            or_(
                User.email.ilike(needle),
                User.full_name.ilike(needle),
                cast(EkycSession.request_id, String).ilike(needle),
                cast(EkycSession.id, String).ilike(needle),
                cast(EkycResult.document_result, String).ilike(needle),
                cast(EkycResult.raw_result, String).ilike(needle),
            )
        )

    for query_filter in filters:
        statement = statement.where(query_filter)
        count_statement = count_statement.where(query_filter)

    count = session.exec(count_statement).one()
    if sort == "oldest":
        statement = statement.order_by(EkycSession.created_at.asc())  # type: ignore[union-attr]
    else:
        statement = statement.order_by(EkycSession.created_at.desc())  # type: ignore[union-attr]
    statement = statement.offset(skip).limit(limit)

    sessions = session.exec(statement).all()
    for ekyc_session in sessions:
        if ekyc_session.owner:
            continue
        if ekyc_session.user_id:
            ekyc_session.owner = session.get(User, ekyc_session.user_id)
    return EkycRequestsAdminPublic(
        data=[_request_admin_public(session, ekyc_session) for ekyc_session in sessions],
        count=count,
    )


@router.get("/me/status")
def read_my_ekyc_status(
    session: SessionDep,
    current_user: CurrentUser,
) -> Any:
    verified_identity = _latest_verified_identity(
        db_session=session,
        user_id=current_user.id,
    )
    latest_session = _latest_user_session(
        db_session=session,
        user_id=current_user.id,
    )
    return {
        "is_verified": verified_identity is not None,
        "verified_at": verified_identity.verified_at if verified_identity else None,
        "document_type": verified_identity.document_type if verified_identity else None,
        "latest_request": _request_public(latest_session) if latest_session else None,
    }


@router.get("/me/identity", response_model=MyVerifiedIdentityPublic)
def read_my_verified_identity(
    session: SessionDep,
    current_user: CurrentUser,
    reveal: bool = False,
) -> Any:
    verified_identity = _latest_verified_identity(
        db_session=session,
        user_id=current_user.id,
    )
    if verified_identity is None:
        return MyVerifiedIdentityPublic(is_verified=False)

    fields = _verified_identity_document_fields(verified_identity, reveal=reveal)
    identity_number = _identity_number_from_verified_identity(
        verified_identity,
        reveal=reveal,
    ) or _first_field_value(fields, "id_number", "passport_number", "document_number")
    place_of_residence = _first_field_value(
        fields,
        "place_of_residence",
        "address",
    )
    place_of_origin = _first_field_value(fields, "place_of_origin")

    return MyVerifiedIdentityPublic(
        is_verified=True,
        document_type=verified_identity.document_type,
        identity_number=identity_number if reveal else _mask_identity_number(identity_number),
        full_name=verified_identity.full_name
        or _first_field_value(fields, "full_name"),
        birth_date=verified_identity.birth_date
        or _first_field_value(fields, "date_of_birth", "birth_year"),
        gender=verified_identity.gender
        or _first_field_value(fields, "sex", "gender"),
        nationality=verified_identity.nationality
        or _first_field_value(fields, "nationality"),
        address=place_of_residence or place_of_origin,
        place_of_origin=place_of_origin,
        place_of_residence=place_of_residence,
        issued_date=verified_identity.issued_date
        or _first_field_value(fields, "issue_date"),
        issue_place=_first_field_value(fields, "issue_place"),
        expired_date=verified_identity.expired_date
        or _first_field_value(fields, "expiry_date", "expired_date"),
        verified_at=verified_identity.verified_at,
    )


@router.get("/voice-challenge")
async def read_voice_challenge(
    _current_user: CurrentUser,
) -> dict[str, str]:
    challenge = await _fetch_voice_challenge_from_ai()
    if challenge is not None:
        return challenge

    return {
        "expected_text": random.choice(VOICE_CHALLENGE_FALLBACKS),
        "instruction": "Please read the phrase aloud while recording your face and voice video.",
    }


@router.post("/voice-session", response_model=EkycVoiceSessionPublic)
def create_voice_session(
    session: SessionDep,
    current_user: CurrentUser,
) -> Any:
    existing_voice_session = _active_pending_voice_session(
        db_session=session,
        current_user=current_user,
    )
    if existing_voice_session is not None:
        return _voice_session_public(existing_voice_session)

    voice_session = _new_voice_session(current_user=current_user)
    session.add(voice_session)
    session.commit()
    session.refresh(voice_session)
    return _voice_session_public(voice_session)


@router.post(
    "/voice-session/{voice_session_id}/verify",
    response_model=EkycVoiceVerifyResponse,
)
async def verify_voice_session(
    session: SessionDep,
    current_user: CurrentUser,
    voice_session_id: uuid.UUID,
    liveness_file: UploadFile = File(description="Video containing face and voice"),
) -> Any:
    voice_session = _get_voice_session_or_404(
        db_session=session,
        current_user=current_user,
        voice_session_id=voice_session_id,
    )
    now = get_datetime_utc()
    if voice_session.status == EkycVoiceSessionStatus.PASSED:
        public_data = _voice_session_public(voice_session).model_dump()
        return EkycVoiceVerifyResponse(
            **public_data,
            verified=True,
            can_continue=True,
            reset_required=False,
            decision="match",
        )
    if voice_session.status in {
        EkycVoiceSessionStatus.FAILED,
        EkycVoiceSessionStatus.EXPIRED,
    }:
        public_data = _voice_session_public(voice_session).model_dump()
        return EkycVoiceVerifyResponse(
            **public_data,
            verified=False,
            can_continue=False,
            reset_required=True,
            decision="failed",
            warning="Step 2 must be restarted.",
        )
    if _as_aware_utc(voice_session.expires_at) <= now:
        _mark_voice_session_expired(db_session=session, voice_session=voice_session)
        public_data = _voice_session_public(voice_session).model_dump()
        return EkycVoiceVerifyResponse(
            **public_data,
            verified=False,
            can_continue=False,
            reset_required=True,
            decision="expired",
            warning="Voice challenge expired. Please start Step 2 again.",
        )

    video_content = await _read_video_upload_bytes(
        liveness_file,
        label="Face and voice video",
        max_size_mb=settings.MAX_VIDEO_UPLOAD_SIZE_MB,
    )
    try:
        ai_payload = await _verify_voice_with_ai(
            file_content=video_content,
            filename=liveness_file.filename or "liveness.mp4",
            content_type=(liveness_file.content_type or "video/mp4").split(";", 1)[0],
            expected_text=voice_session.expected_text,
        )
    except HTTPException as exc:
        if exc.status_code < 500:
            raise
        logger.warning(
            "Voice verification service failed; returning retry response: %s",
            exc.detail,
        )
        return _voice_retry_response(
            db_session=session,
            voice_session=voice_session,
            decision="unavailable",
            warning=f"{exc.detail} Please record again.",
        )
    except Exception as exc:
        logger.exception("Unexpected voice verification failure")
        return _voice_retry_response(
            db_session=session,
            voice_session=voice_session,
            decision="unavailable",
            warning=(
                "Voice verification could not be completed. "
                f"Please record again. ({type(exc).__name__})"
            ),
        )
    decision = _voice_ai_decision(ai_payload)
    voice_session.ai_result = ai_payload
    voice_session.updated_at = get_datetime_utc()
    video_hash = sha256(video_content).hexdigest()

    if decision == "match":
        voice_session.status = EkycVoiceSessionStatus.PASSED
        voice_session.verified_at = get_datetime_utc()
        voice_session.liveness_video_hash = video_hash
        session.add(voice_session)
        session.commit()
        session.refresh(voice_session)
        public_data = _voice_session_public(voice_session).model_dump()
        return EkycVoiceVerifyResponse(
            **public_data,
            verified=True,
            can_continue=True,
            reset_required=False,
            decision=decision,
        )

    verified_against_text = voice_session.display_text
    verified_against_hint = voice_session.spoken_hint
    voice_session.attempts += 1
    warning = (
        "The spoken digits did not match. Please read the new digits one by one."
    )
    reset_required = voice_session.attempts >= voice_session.max_attempts
    if reset_required:
        voice_session.status = EkycVoiceSessionStatus.FAILED
        warning = "Voice verification failed 3 times. Please restart Step 2."
    else:
        _refresh_voice_challenge(voice_session)

    session.add(voice_session)
    session.commit()
    session.refresh(voice_session)
    public_data = _voice_session_public(voice_session).model_dump()
    return EkycVoiceVerifyResponse(
        **public_data,
        verified=False,
        can_continue=False,
        reset_required=reset_required,
        decision=decision or "failed",
        warning=warning,
        verified_against_text=verified_against_text,
        verified_against_hint=verified_against_hint,
    )


@router.post(
    "",
    response_model=EkycRequestCreateResponse,
    status_code=202,
    include_in_schema=False,
)
@router.post("/", response_model=EkycRequestCreateResponse, status_code=202)
async def create_ekyc_request(
    session: SessionDep,
    current_user: CurrentUser,
    file: UploadFile | None = File(
        default=None,
        description="Legacy front image field. Prefer front_image.",
    ),
    front_image: UploadFile | None = File(default=None),
    back_image: UploadFile | None = File(default=None),
    front_file: UploadFile | None = File(default=None),
    back_file: UploadFile | None = File(default=None),
    liveness_file: UploadFile | None = File(default=None),
    video_file: UploadFile | None = File(
        default=None,
        description="Legacy liveness video field. Prefer liveness_file.",
    ),
    document_type: EkycDocumentType = Form(default=EkycDocumentType.CCCD),
    expected_text: str | None = Form(default=None),
    voice_challenge_text: str | None = Form(default=None),
    voice_session_id: uuid.UUID | None = Form(default=None),
) -> Any:
    logger.info("Received eKYC upload")
    if _latest_verified_identity(db_session=session, user_id=current_user.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Your identity has already been verified.",
        )

    front_upload = front_image or front_file or file
    back_upload = back_image or back_file
    liveness_upload = liveness_file or video_file
    submission_voice_session = (
        _submission_voice_session_or_400(
            db_session=session,
            current_user=current_user,
            voice_session_id=voice_session_id,
        )
        if voice_session_id is not None
        else None
    )
    challenge_text = (
        submission_voice_session.expected_text
        if submission_voice_session is not None
        else (expected_text or voice_challenge_text or "").strip()
    )
    if front_upload is None or back_upload is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please upload both the front and back document images.",
        )
    if liveness_upload is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please upload a face verification video.",
        )
    if not challenge_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please read the generated voice challenge before submitting.",
        )

    front_extension = _validate_upload_metadata(front_upload, label="Front document image")
    back_extension = _validate_upload_metadata(back_upload, label="Back document image")
    liveness_extension = _validate_video_metadata(liveness_upload)
    request_id = uuid.uuid4()
    upload_root = Path(settings.UPLOAD_DIR)
    request_upload_dir = upload_root / str(request_id)
    file_prefix = document_type.value.lower()
    front_image_path = request_upload_dir / f"{file_prefix}_front{front_extension}"
    back_image_path = request_upload_dir / f"{file_prefix}_back{back_extension}"
    liveness_path = request_upload_dir / f"liveness{liveness_extension}"

    try:
        await _save_upload_file(
            front_upload,
            front_image_path,
            label="Front document image",
            max_size_mb=settings.MAX_UPLOAD_SIZE_MB,
        )
        await _save_upload_file(
            back_upload,
            back_image_path,
            label="Back document image",
            max_size_mb=settings.MAX_UPLOAD_SIZE_MB,
        )
        await _save_upload_file(
            liveness_upload,
            liveness_path,
            label="Face verification video",
            max_size_mb=settings.MAX_VIDEO_UPLOAD_SIZE_MB,
        )
        if liveness_path.stat().st_size < MIN_VIDEO_UPLOAD_SIZE_BYTES:
            liveness_path.unlink(missing_ok=True)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Face verification video did not contain video data. Please record again.",
            )
        if (
            submission_voice_session is not None
            and submission_voice_session.status == EkycVoiceSessionStatus.PASSED
            and submission_voice_session.liveness_video_hash
        ):
            submitted_video_hash = _file_sha256(liveness_path)
            if submitted_video_hash != submission_voice_session.liveness_video_hash:
                liveness_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="The submitted video does not match the passed Step 2 voice session.",
                )
    except HTTPException:
        shutil.rmtree(request_upload_dir, ignore_errors=True)
        raise
    logger.info("Saved eKYC images for request %s", request_id)

    ekyc_session = EkycSession(
        request_id=request_id,
        user_id=current_user.id,
        status=EkycRequestStatus.PENDING,
        document_type=document_type,
        model_version=settings.AI_MODEL_VERSION,
    )
    session.add(ekyc_session)
    session.commit()
    session.refresh(ekyc_session)

    uploaded_files = [
        EkycFile(
            session_id=ekyc_session.id,
            file_type=EkycFileType.DOCUMENT_FRONT,
            file_path=str(front_image_path),
            content_type=front_upload.content_type,
            size_bytes=front_image_path.stat().st_size,
        ),
        EkycFile(
            session_id=ekyc_session.id,
            file_type=EkycFileType.DOCUMENT_BACK,
            file_path=str(back_image_path),
            content_type=back_upload.content_type,
            size_bytes=back_image_path.stat().st_size,
        ),
        EkycFile(
            session_id=ekyc_session.id,
            file_type=EkycFileType.LIVENESS_VIDEO,
            file_path=str(liveness_path),
            content_type=liveness_upload.content_type,
            size_bytes=liveness_path.stat().st_size,
        ),
    ]
    session.add_all(uploaded_files)
    session.commit()
    session.refresh(ekyc_session)
    logger.info("Created eKYC request %s", request_id)

    payload = {
        "request_id": str(request_id),
        "image_path": str(front_image_path),
        "front_image_path": str(front_image_path),
        "back_image_path": str(back_image_path),
        "liveness_path": str(liveness_path),
        "expected_text": challenge_text,
        "voice_session_id": str(submission_voice_session.id)
        if submission_voice_session is not None
        else None,
        "document_type": document_type.value,
        "document_type_hint": _ai_document_type(document_type),
        "job_type": "EKYC_VERIFY_ALL",
    }
    try:
        enqueue_ekyc_job(payload)
    except (EkycQueueError, OSError) as exc:
        logger.exception("Failed to push eKYC job to Redis for request %s", request_id)
        ekyc_session.status = EkycRequestStatus.FAILED
        ekyc_session.error_message = "We could not enqueue the eKYC request for processing."
        ekyc_session.updated_at = get_datetime_utc()
        session.add(ekyc_session)
        session.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The eKYC processing queue is temporarily unavailable.",
        ) from exc

    if submission_voice_session is not None:
        session.delete(submission_voice_session)
        session.commit()

    logger.info("Pushed eKYC job to Redis for request %s", request_id)
    return EkycRequestCreateResponse(
        request_id=request_id,
        status=EkycRequestStatus.PENDING,
        document_type=document_type,
        message=_status_message(EkycRequestStatus.PENDING),
    )


@router.get("/{request_id}", response_model=EkycRequestPublic)
def read_ekyc_request(
    session: SessionDep,
    current_user: CurrentUser,
    request_id: uuid.UUID,
) -> Any:
    ekyc_session = _get_session_or_404(
        db_session=session,
        current_user=current_user,
        request_id=request_id,
    )

    return _request_public(ekyc_session)


@router.get(
    "/{request_id}/admin-detail",
    dependencies=[Depends(get_current_ekyc_reviewer)],
    response_model=EkycRequestAdminPublic,
)
def read_ekyc_request_admin_detail(
    session: SessionDep,
    request_id: uuid.UUID,
) -> Any:
    statement = select(EkycSession).where(EkycSession.request_id == request_id)
    ekyc_session = session.exec(statement).first()
    if not ekyc_session:
        raise HTTPException(status_code=404, detail="eKYC request not found")
    if ekyc_session.user_id:
        ekyc_session.owner = session.get(User, ekyc_session.user_id)
    return _request_admin_public(session, ekyc_session)


@router.post(
    "/{request_id}/ai-review",
    dependencies=[Depends(get_current_ekyc_reviewer)],
    response_model=EkycRequestAdminPublic,
)
async def generate_ekyc_ai_admin_review(
    session: SessionDep,
    request_id: uuid.UUID,
    current_user: User = Depends(get_current_ekyc_reviewer),
) -> Any:
    statement = select(EkycSession).where(EkycSession.request_id == request_id)
    ekyc_session = session.exec(statement).first()
    if not ekyc_session:
        raise HTTPException(status_code=404, detail="eKYC request not found")
    if ekyc_session.user_id:
        ekyc_session.owner = session.get(User, ekyc_session.user_id)

    latest_result = _latest_result(ekyc_session)
    if latest_result is None and not isinstance(ekyc_session.result, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Hồ sơ chưa có kết quả AI để phân tích.",
        )

    unified = _unified_result_for_admin_review(ekyc_session, latest_result)
    try:
        ai_review = await request_admin_ai_review(unified_result=unified)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    now = get_datetime_utc()
    if latest_result:
        raw_result = (
            latest_result.raw_result if isinstance(latest_result.raw_result, dict) else {}
        )
        latest_result.raw_result = {**raw_result, "ai_admin_review": ai_review}
        session.add(latest_result)

    session_result = ekyc_session.result if isinstance(ekyc_session.result, dict) else {}
    ekyc_session.result = {**session_result, "ai_admin_review": ai_review}
    ekyc_session.updated_at = now
    create_admin_audit_log(
        session=session,
        actor=current_user,
        action="ekyc.ai_review",
        target_type="ekyc_request",
        target_id=str(ekyc_session.request_id),
        target_label=ekyc_session.owner.email if ekyc_session.owner else None,
        details={
            "recommendation": ai_review.get("recommendation"),
            "confidence": ai_review.get("confidence"),
        },
    )
    session.add(ekyc_session)
    session.commit()
    session.refresh(ekyc_session)
    if ekyc_session.user_id:
        ekyc_session.owner = session.get(User, ekyc_session.user_id)
    return _request_admin_public(session, ekyc_session)


@router.patch(
    "/{request_id}/document-fields",
    response_model=EkycRequestAdminPublic,
)
def update_ekyc_request_document_fields(
    session: SessionDep,
    request_id: uuid.UUID,
    payload: EkycDocumentFieldsAdminUpdate,
    current_user: User = Depends(get_current_ekyc_reviewer),
) -> Any:
    statement = select(EkycSession).where(EkycSession.request_id == request_id)
    ekyc_session = session.exec(statement).first()
    if not ekyc_session:
        raise HTTPException(status_code=404, detail="eKYC request not found")
    if ekyc_session.user_id:
        ekyc_session.owner = session.get(User, ekyc_session.user_id)

    latest_result = _latest_result(ekyc_session)
    if latest_result is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot edit document fields before OCR result is available.",
        )
    private_document_result = (
        decrypt_document_payload(latest_result.encrypted_document_result)
        if latest_result and latest_result.encrypted_document_result
        else None
    )
    if private_document_result is None:
        private_document_result = _private_record_document_payload(latest_result)
    if (
        latest_result
        and latest_result.encrypted_document_result
        and private_document_result is None
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot decrypt original document data for editing.",
        )
    current_document_result = private_document_result or _document_result_for_identity(
        ekyc_session,
        latest_result,
    )
    current_fields = _document_fields(current_document_result)
    updated_fields = _clean_admin_document_fields(payload, current_fields)
    if not updated_fields:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one document field is required.",
        )

    now = get_datetime_utc()
    _store_admin_document_fields(
        ekyc_session=ekyc_session,
        latest_result=latest_result,
        private_document_result=current_document_result,
        fields=updated_fields,
        confirmed_at=now,
    )
    ekyc_session.updated_at = now

    create_admin_audit_log(
        session=session,
        actor=current_user,
        action="ekyc.document_fields_update",
        target_type="ekyc_request",
        target_id=str(ekyc_session.request_id),
        target_label=ekyc_session.owner.email if ekyc_session.owner else None,
        details={
            "fields": sorted(updated_fields.keys()),
            "user_id": str(ekyc_session.user_id) if ekyc_session.user_id else None,
        },
    )
    if latest_result:
        session.add(latest_result)
    session.add(ekyc_session)
    session.commit()
    session.refresh(ekyc_session)
    if latest_result:
        session.refresh(latest_result)
        ekyc_session.results = [latest_result]
    if ekyc_session.user_id:
        ekyc_session.owner = session.get(User, ekyc_session.user_id)
    return _request_admin_public(session, ekyc_session)


@router.post(
    "/{request_id}/approve",
    response_model=EkycRequestAdminPublic,
)
def approve_ekyc_request(
    session: SessionDep,
    request_id: uuid.UUID,
    payload: EkycManualDecisionPayload,
    current_user: User = Depends(get_current_ekyc_reviewer),
) -> Any:
    statement = select(EkycSession).where(EkycSession.request_id == request_id)
    ekyc_session = session.exec(statement).first()
    if not ekyc_session:
        raise HTTPException(status_code=404, detail="eKYC request not found")
    if ekyc_session.user_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot approve an eKYC request without an owner user.",
        )

    latest_result = _latest_result(ekyc_session)
    document_result = _document_result_for_identity(ekyc_session, latest_result)
    if not _has_document_number(document_result):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot approve because the document number is missing from OCR data.",
        )

    result = _upsert_manual_result(
        db_session=session,
        current_user=current_user,
        ekyc_session=ekyc_session,
        status_value=EkycRequestStatus.SUCCESS,
        decision="match",
        reason=(payload.reason or "").strip() or None,
    )
    _save_manual_verified_identity(
        db_session=session,
        ekyc_session=ekyc_session,
        result=result,
    )

    now = get_datetime_utc()
    ekyc_session.status = EkycRequestStatus.SUCCESS
    ekyc_session.decision = "match"
    ekyc_session.error_message = None
    ekyc_session.updated_at = now
    ekyc_session.processed_at = now
    create_admin_audit_log(
        session=session,
        actor=current_user,
        action="ekyc.approve",
        target_type="ekyc_request",
        target_id=str(ekyc_session.request_id),
        target_label=ekyc_session.owner.email if ekyc_session.owner else None,
        details={
            "reason": (payload.reason or "").strip() or None,
            "status": EkycRequestStatus.SUCCESS.value,
            "user_id": str(ekyc_session.user_id) if ekyc_session.user_id else None,
        },
    )
    create_user_notification(
        session=session,
        user_id=ekyc_session.user_id,
        type="ekyc_approved",
        title="eKYC approved",
        message="Your identity verification has been approved.",
        data={
            "request_id": str(ekyc_session.request_id),
            "href": "/ekyc",
        },
    )
    session.add(ekyc_session)
    session.commit()
    session.refresh(ekyc_session)
    ekyc_session.results = [result]
    if ekyc_session.user_id:
        ekyc_session.owner = session.get(User, ekyc_session.user_id)
    return _request_admin_public(session, ekyc_session)


@router.post(
    "/{request_id}/reject",
    response_model=EkycRequestAdminPublic,
)
def reject_ekyc_request(
    session: SessionDep,
    request_id: uuid.UUID,
    payload: EkycManualDecisionPayload,
    current_user: User = Depends(get_current_ekyc_reviewer),
) -> Any:
    reason = (payload.reason or "").strip()
    if not reason:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A rejection reason is required.",
        )

    statement = select(EkycSession).where(EkycSession.request_id == request_id)
    ekyc_session = session.exec(statement).first()
    if not ekyc_session:
        raise HTTPException(status_code=404, detail="eKYC request not found")
    if ekyc_session.user_id:
        ekyc_session.owner = session.get(User, ekyc_session.user_id)

    result = _upsert_manual_result(
        db_session=session,
        current_user=current_user,
        ekyc_session=ekyc_session,
        status_value=EkycRequestStatus.FAILED,
        decision="not_match",
        reason=reason,
    )
    _revoke_verified_identity_for_result(db_session=session, result_id=result.id)

    now = get_datetime_utc()
    ekyc_session.status = EkycRequestStatus.FAILED
    ekyc_session.decision = "not_match"
    ekyc_session.error_message = reason
    ekyc_session.updated_at = now
    ekyc_session.processed_at = now
    create_admin_audit_log(
        session=session,
        actor=current_user,
        action="ekyc.reject",
        target_type="ekyc_request",
        target_id=str(ekyc_session.request_id),
        target_label=ekyc_session.owner.email if ekyc_session.owner else None,
        details={
            "reason": reason,
            "status": EkycRequestStatus.FAILED.value,
            "user_id": str(ekyc_session.user_id) if ekyc_session.user_id else None,
        },
    )
    if ekyc_session.user_id:
        create_user_notification(
            session=session,
            user_id=ekyc_session.user_id,
            type="ekyc_rejected",
            title="eKYC rejected",
            message=f"Your identity verification was rejected: {reason}",
            data={
                "request_id": str(ekyc_session.request_id),
                "href": "/ekyc",
                "reason": reason,
            },
        )
    session.add(ekyc_session)
    session.commit()
    session.refresh(ekyc_session)
    ekyc_session.results = [result]
    if ekyc_session.user_id:
        ekyc_session.owner = session.get(User, ekyc_session.user_id)
    return _request_admin_public(session, ekyc_session)


@router.post(
    "/{request_id}/retry",
    response_model=EkycRequestAdminPublic,
)
def retry_ekyc_request(
    session: SessionDep,
    request_id: uuid.UUID,
    current_user: User = Depends(get_current_ekyc_reviewer),
) -> Any:
    statement = select(EkycSession).where(EkycSession.request_id == request_id)
    ekyc_session = session.exec(statement).first()
    if not ekyc_session:
        raise HTTPException(status_code=404, detail="eKYC request not found")
    if ekyc_session.user_id:
        ekyc_session.owner = session.get(User, ekyc_session.user_id)

    processing_timeout_minutes = get_ekyc_processing_timeout_minutes(session)
    can_retry = ekyc_session.status in RETRYABLE_STATUSES or _is_processing_stale(
        ekyc_session,
        processing_timeout_minutes,
    )
    if not can_retry:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Only FAILED, MANUAL_REVIEW, or stale PROCESSING eKYC requests "
                "can be retried."
            ),
        )

    payload = _retry_payload_or_400(ekyc_session)
    latest_result = _latest_result(ekyc_session)
    previous_status = ekyc_session.status
    now = get_datetime_utc()

    if latest_result:
        latest_result.status = EkycRequestStatus.PENDING
        latest_result.decision = None
        latest_result.error_message = None
        latest_result.completed_at = None
        raw_result = latest_result.raw_result if isinstance(latest_result.raw_result, dict) else {}
        latest_result.raw_result = {
            **raw_result,
            "retry": {
                "requested_at": now.isoformat(),
                "requested_by": current_user.email,
            },
        }
        session.add(latest_result)

    ekyc_session.status = EkycRequestStatus.PENDING
    ekyc_session.decision = None
    ekyc_session.error_message = None
    ekyc_session.updated_at = now
    ekyc_session.processed_at = None
    create_admin_audit_log(
        session=session,
        actor=current_user,
        action="ekyc.retry",
        target_type="ekyc_request",
        target_id=str(ekyc_session.request_id),
        target_label=ekyc_session.owner.email if ekyc_session.owner else None,
        details={
            "previous_status": previous_status.value,
            "processing_timeout_minutes": processing_timeout_minutes,
            "status": EkycRequestStatus.PENDING.value,
            "user_id": str(ekyc_session.user_id) if ekyc_session.user_id else None,
        },
    )

    try:
        enqueue_ekyc_job(payload)
    except (EkycQueueError, OSError) as exc:
        logger.exception("Failed to retry eKYC job for request %s", request_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The eKYC processing queue is temporarily unavailable.",
        ) from exc

    session.add(ekyc_session)
    session.commit()
    session.refresh(ekyc_session)
    if latest_result:
        ekyc_session.results = [latest_result]
    if ekyc_session.user_id:
        ekyc_session.owner = session.get(User, ekyc_session.user_id)
    return _request_admin_public(session, ekyc_session)


@router.get(
    "/{request_id}/files/{file_kind}",
    dependencies=[Depends(get_current_ekyc_reviewer)],
)
def read_ekyc_request_file(
    session: SessionDep,
    request_id: uuid.UUID,
    file_kind: str,
) -> Any:
    file_type = ADMIN_FILE_KIND_TO_TYPE.get(file_kind)
    if file_type is None:
        raise HTTPException(status_code=404, detail="eKYC file not found")

    statement = select(EkycSession).where(EkycSession.request_id == request_id)
    ekyc_session = session.exec(statement).first()
    if not ekyc_session:
        raise HTTPException(status_code=404, detail="eKYC request not found")

    ekyc_file = _ekyc_file(ekyc_session, file_type)
    if not ekyc_file:
        raise HTTPException(status_code=404, detail="eKYC file not found")

    file_path = Path(ekyc_file.file_path)
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="eKYC file is not available")

    return FileResponse(
        file_path,
        media_type=ekyc_file.content_type or "application/octet-stream",
        filename=file_path.name,
    )


@router.delete(
    "/{request_id}",
    response_model=Message,
)
def delete_ekyc_request(
    session: SessionDep,
    request_id: uuid.UUID,
    current_user: User = Depends(get_current_ekyc_reviewer),
) -> Any:
    statement = select(EkycSession).where(EkycSession.request_id == request_id)
    ekyc_session = session.exec(statement).first()
    if not ekyc_session:
        raise HTTPException(status_code=404, detail="eKYC request not found")
    if ekyc_session.user_id:
        ekyc_session.owner = session.get(User, ekyc_session.user_id)

    upload_directories = _session_upload_directories(ekyc_session)
    result_ids = session.exec(
        select(EkycResult.id).where(EkycResult.session_id == ekyc_session.id)
    ).all()
    create_admin_audit_log(
        session=session,
        actor=current_user,
        action="ekyc.delete",
        target_type="ekyc_request",
        target_id=str(ekyc_session.request_id),
        target_label=ekyc_session.owner.email if ekyc_session.owner else None,
        details={
            "status": ekyc_session.status.value,
            "user_id": str(ekyc_session.user_id) if ekyc_session.user_id else None,
        },
    )
    _revoke_verified_identities_for_results(
        db_session=session,
        result_ids=result_ids,
    )
    session.flush()
    session.exec(delete(EkycFile).where(EkycFile.session_id == ekyc_session.id))
    session.exec(delete(EkycResult).where(EkycResult.session_id == ekyc_session.id))
    session.exec(delete(EkycSession).where(EkycSession.id == ekyc_session.id))
    session.commit()

    for directory in upload_directories:
        shutil.rmtree(directory, ignore_errors=True)

    return Message(message="eKYC request deleted successfully")
