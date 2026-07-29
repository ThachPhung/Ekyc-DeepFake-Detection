import uuid
from datetime import timedelta
from hashlib import sha256

import httpx
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.api.routes import ekyc_requests
from app.core.config import settings
from app.models import (
    EkycFile,
    EkycFileType,
    EkycRequestStatus,
    EkycResult,
    EkycSession,
    EkycVoiceSession,
    EkycVoiceSessionStatus,
    VerifiedIdentity,
    get_datetime_utc,
)
from tests.utils.user import authentication_token_from_email, create_random_user


def test_delete_ekyc_request_removes_record_and_uploads(
    client: TestClient,
    db: Session,
    monkeypatch,
    superuser_token_headers: dict[str, str],
    tmp_path,
) -> None:
    upload_root = tmp_path / "ekyc"
    request_upload_dir = upload_root / str(uuid.uuid4())
    request_upload_dir.mkdir(parents=True)
    front_image = request_upload_dir / "document_front.jpg"
    front_image.write_bytes(b"fake image")
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(upload_root))

    ekyc_session = EkycSession()
    db.add(ekyc_session)
    db.commit()
    db.refresh(ekyc_session)

    ekyc_file = EkycFile(
        session_id=ekyc_session.id,
        file_type=EkycFileType.DOCUMENT_FRONT,
        file_path=str(front_image),
        content_type="image/jpeg",
        size_bytes=front_image.stat().st_size,
    )
    db.add(ekyc_file)
    db.commit()

    response = client.delete(
        f"{settings.API_V1_STR}/ekyc/requests/{ekyc_session.request_id}",
        headers=superuser_token_headers,
    )

    assert response.status_code == 200
    assert response.json()["message"] == "eKYC request deleted successfully"
    assert db.get(EkycSession, ekyc_session.id) is None
    assert db.get(EkycFile, ekyc_file.id) is None
    assert not request_upload_dir.exists()


def test_delete_ekyc_request_revokes_verified_identity(
    client: TestClient,
    db: Session,
    superuser_token_headers: dict[str, str],
) -> None:
    user = create_random_user(db)
    user_headers = authentication_token_from_email(
        client=client,
        email=user.email,
        db=db,
    )
    ekyc_session = EkycSession(
        user_id=user.id,
        status=EkycRequestStatus.SUCCESS,
    )
    db.add(ekyc_session)
    db.commit()
    db.refresh(ekyc_session)

    ekyc_result = EkycResult(
        session_id=ekyc_session.id,
        user_id=user.id,
        status=EkycRequestStatus.SUCCESS,
        decision="approved",
    )
    db.add(ekyc_result)
    db.commit()
    db.refresh(ekyc_result)

    verified_identity = VerifiedIdentity(
        user_id=user.id,
        ekyc_result_id=ekyc_result.id,
        identity_number_hash="verified-id-hash",
    )
    db.add(verified_identity)
    db.commit()
    db.refresh(verified_identity)

    response = client.delete(
        f"{settings.API_V1_STR}/ekyc/requests/{ekyc_session.request_id}",
        headers=superuser_token_headers,
    )

    assert response.status_code == 200
    stored_identity = db.get(VerifiedIdentity, verified_identity.id)
    assert stored_identity is not None
    assert stored_identity.revoked_at is not None

    status_response = client.get(
        f"{settings.API_V1_STR}/ekyc/requests/me/status",
        headers=user_headers,
    )

    assert status_response.status_code == 200
    assert status_response.json()["is_verified"] is False
    assert status_response.json()["latest_request"] is None


def test_my_ekyc_status_ignores_orphan_verified_identity(
    client: TestClient,
    db: Session,
) -> None:
    user = create_random_user(db)
    user_headers = authentication_token_from_email(
        client=client,
        email=user.email,
        db=db,
    )
    verified_identity = VerifiedIdentity(
        user_id=user.id,
        ekyc_result_id=None,
        identity_number_hash="orphaned-id-hash",
    )
    db.add(verified_identity)
    db.commit()

    status_response = client.get(
        f"{settings.API_V1_STR}/ekyc/requests/me/status",
        headers=user_headers,
    )

    assert status_response.status_code == 200
    assert status_response.json()["is_verified"] is False
    assert status_response.json()["latest_request"] is None


def test_create_voice_session_reuses_active_pending_session(
    client: TestClient,
    db: Session,
) -> None:
    user = create_random_user(db)
    user_headers = authentication_token_from_email(
        client=client,
        email=user.email,
        db=db,
    )

    first_response = client.post(
        f"{settings.API_V1_STR}/ekyc/requests/voice-session",
        headers=user_headers,
    )
    second_response = client.post(
        f"{settings.API_V1_STR}/ekyc/requests/voice-session",
        headers=user_headers,
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    first_payload = first_response.json()
    second_payload = second_response.json()
    assert second_payload["session_id"] == first_payload["session_id"]
    assert second_payload["display_digits"] == first_payload["display_digits"]

    stored_sessions = db.exec(
        select(EkycVoiceSession).where(EkycVoiceSession.user_id == user.id)
    ).all()
    assert len(stored_sessions) == 1


def test_refresh_voice_challenge_forces_new_digits_when_generator_repeats(
    monkeypatch,
) -> None:
    voice_session = EkycVoiceSession(
        display_digits=["1", "1", "1", "1", "1", "1"],
        display_text="1 1 1 1 1 1",
        expected_text="mot mot mot mot mot mot",
        spoken_hint="mot - mot - mot - mot - mot - mot",
    )

    def _repeat_challenge() -> tuple[list[str], str, str, str]:
        return (
            ["1", "1", "1", "1", "1", "1"],
            "1 1 1 1 1 1",
            "mot mot mot mot mot mot",
            "mot - mot - mot - mot - mot - mot",
        )

    monkeypatch.setattr(
        ekyc_requests,
        "_generate_digit_voice_challenge",
        _repeat_challenge,
    )

    ekyc_requests._refresh_voice_challenge(voice_session)

    assert voice_session.display_digits == ["1", "1", "1", "1", "1", "2"]
    assert voice_session.display_text == "1 1 1 1 1 2"
    assert voice_session.expected_text == "mot mot mot mot mot hai"
    assert voice_session.spoken_hint == "mot - mot - mot - mot - mot - hai"


def test_verify_voice_failure_returns_checked_and_next_digits(
    client: TestClient,
    db: Session,
    monkeypatch,
) -> None:
    user = create_random_user(db)
    user_headers = authentication_token_from_email(
        client=client,
        email=user.email,
        db=db,
    )

    create_response = client.post(
        f"{settings.API_V1_STR}/ekyc/requests/voice-session",
        headers=user_headers,
    )
    assert create_response.status_code == 200
    created_payload = create_response.json()
    checked_text = created_payload["display_text"]
    checked_hint = created_payload["spoken_hint"]

    async def _fake_verify_voice_with_ai(**_kwargs) -> dict:
        return {
            "success": False,
            "voice_passed": False,
            "voice_decision": "failed",
        }

    def _fake_refresh_voice_challenge(voice_session: EkycVoiceSession) -> None:
        voice_session.display_digits = ["9", "8", "8", "2", "1", "2"]
        voice_session.display_text = "9 8 8 2 1 2"
        voice_session.expected_text = "chin tam tam hai mot hai"
        voice_session.spoken_hint = "chin - tam - tam - hai - mot - hai"

    monkeypatch.setattr(
        ekyc_requests,
        "_verify_voice_with_ai",
        _fake_verify_voice_with_ai,
    )
    monkeypatch.setattr(
        ekyc_requests,
        "_refresh_voice_challenge",
        _fake_refresh_voice_challenge,
    )

    verify_response = client.post(
        (
            f"{settings.API_V1_STR}/ekyc/requests/voice-session/"
            f"{created_payload['session_id']}/verify"
        ),
        headers=user_headers,
        files={"liveness_file": ("live.mp4", b"x" * 2048, "video/mp4")},
    )

    assert verify_response.status_code == 200
    payload = verify_response.json()
    assert payload["verified"] is False
    assert payload["attempts"] == 1
    assert payload["verified_against_text"] == checked_text
    assert payload["verified_against_hint"] == checked_hint
    assert payload["display_text"] == "9 8 8 2 1 2"
    assert payload["spoken_hint"] == "chin - tam - tam - hai - mot - hai"


def test_verify_voice_expired_session_requires_restart(
    client: TestClient,
    db: Session,
) -> None:
    user = create_random_user(db)
    user_headers = authentication_token_from_email(
        client=client,
        email=user.email,
        db=db,
    )
    voice_session = ekyc_requests._new_voice_session(current_user=user)
    voice_session.expires_at = get_datetime_utc() - timedelta(seconds=1)
    db.add(voice_session)
    db.commit()
    db.refresh(voice_session)

    response = client.post(
        (
            f"{settings.API_V1_STR}/ekyc/requests/voice-session/"
            f"{voice_session.id}/verify"
        ),
        headers=user_headers,
        files={"liveness_file": ("live.mp4", b"x" * 2048, "video/mp4")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["verified"] is False
    assert payload["reset_required"] is True
    assert payload["decision"] == "expired"
    assert payload["warning"] == "Voice challenge expired. Please start Step 2 again."

    db.refresh(voice_session)
    assert voice_session.status == EkycVoiceSessionStatus.EXPIRED


def test_verify_voice_success_stores_video_hash(
    client: TestClient,
    db: Session,
    monkeypatch,
) -> None:
    user = create_random_user(db)
    user_headers = authentication_token_from_email(
        client=client,
        email=user.email,
        db=db,
    )
    create_response = client.post(
        f"{settings.API_V1_STR}/ekyc/requests/voice-session",
        headers=user_headers,
    )
    assert create_response.status_code == 200
    voice_session_id = create_response.json()["session_id"]
    video_content = b"passed-video" * 200

    async def _fake_verify_voice_with_ai(**_kwargs) -> dict:
        return {
            "success": True,
            "voice_passed": True,
            "voice_decision": "match",
            "transcript": "mot hai ba bon nam sau",
            "wer": 0.0,
        }

    monkeypatch.setattr(
        ekyc_requests,
        "_verify_voice_with_ai",
        _fake_verify_voice_with_ai,
    )

    response = client.post(
        f"{settings.API_V1_STR}/ekyc/requests/voice-session/{voice_session_id}/verify",
        headers=user_headers,
        files={"liveness_file": ("live.mp4", video_content, "video/mp4")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["verified"] is True
    assert payload["can_continue"] is True
    assert payload["status"] == EkycVoiceSessionStatus.PASSED

    stored_session = db.get(EkycVoiceSession, uuid.UUID(voice_session_id))
    assert stored_session is not None
    assert stored_session.status == EkycVoiceSessionStatus.PASSED
    assert stored_session.liveness_video_hash == sha256(video_content).hexdigest()


def test_verify_voice_timeout_returns_retry_response(
    client: TestClient,
    db: Session,
    monkeypatch,
) -> None:
    user = create_random_user(db)
    user_headers = authentication_token_from_email(
        client=client,
        email=user.email,
        db=db,
    )
    create_response = client.post(
        f"{settings.API_V1_STR}/ekyc/requests/voice-session",
        headers=user_headers,
    )
    assert create_response.status_code == 200
    created_payload = create_response.json()

    async def _fake_verify_voice_with_ai(**_kwargs) -> dict:
        raise HTTPException(
            status_code=503,
            detail="Voice verification is temporarily unavailable.",
        ) from httpx.ReadTimeout("timed out")

    monkeypatch.setattr(
        ekyc_requests,
        "_verify_voice_with_ai",
        _fake_verify_voice_with_ai,
    )

    verify_response = client.post(
        (
            f"{settings.API_V1_STR}/ekyc/requests/voice-session/"
            f"{created_payload['session_id']}/verify"
        ),
        headers=user_headers,
        files={"liveness_file": ("live.mp4", b"x" * 2048, "video/mp4")},
    )

    assert verify_response.status_code == 200
    payload = verify_response.json()
    assert payload["verified"] is False
    assert payload["decision"] == "unavailable"
    assert payload["warning"] == (
        "Voice verification is temporarily unavailable. Please record again."
    )
    assert payload["attempts"] == 1


def test_create_ekyc_request_rejects_video_that_differs_from_passed_voice_session(
    client: TestClient,
    db: Session,
    monkeypatch,
    tmp_path,
) -> None:
    user = create_random_user(db)
    user_headers = authentication_token_from_email(
        client=client,
        email=user.email,
        db=db,
    )
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path / "uploads"))
    original_video = b"original-passed-video" * 200
    voice_session = ekyc_requests._new_voice_session(current_user=user)
    voice_session.status = EkycVoiceSessionStatus.PASSED
    voice_session.verified_at = get_datetime_utc()
    voice_session.liveness_video_hash = sha256(original_video).hexdigest()
    db.add(voice_session)
    db.commit()
    db.refresh(voice_session)

    response = client.post(
        f"{settings.API_V1_STR}/ekyc/requests/",
        headers=user_headers,
        data={
            "document_type": "CCCD",
            "voice_session_id": str(voice_session.id),
        },
        files={
            "front_image": ("front.jpg", b"front-image", "image/jpeg"),
            "back_image": ("back.jpg", b"back-image", "image/jpeg"),
            "liveness_file": ("live.mp4", b"different-video" * 200, "video/mp4"),
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "The submitted video does not match the passed Step 2 voice session."
    )


def test_my_verified_identity_returns_owned_masked_identity(
    client: TestClient,
    db: Session,
    monkeypatch,
) -> None:
    user = create_random_user(db)
    user_headers = authentication_token_from_email(
        client=client,
        email=user.email,
        db=db,
    )
    ekyc_session = EkycSession(
        user_id=user.id,
        status=EkycRequestStatus.SUCCESS,
    )
    db.add(ekyc_session)
    db.commit()
    db.refresh(ekyc_session)

    ekyc_result = EkycResult(
        session_id=ekyc_session.id,
        user_id=user.id,
        status=EkycRequestStatus.SUCCESS,
        decision="match",
        document_result={
            "parsed_fields": {
                "id_number": "123456789012",
                "full_name": "Nguyen Van A",
                "place_of_origin": "Thanh, Kim Dong, Hung Yen",
                "place_of_residence": "Long Bien, Ha Noi",
                "issue_place": "Cuc Canh Sat",
            }
        },
        encrypted_document_result="document-envelope",
    )
    db.add(ekyc_result)
    db.commit()
    db.refresh(ekyc_result)

    verified_identity = VerifiedIdentity(
        user_id=user.id,
        ekyc_result_id=ekyc_result.id,
        identity_number_hash="owned-id-hash",
        identity_number_encrypted="identity-envelope",
        full_name="Nguyen Van A",
        birth_date="1999-01-01",
        gender="Nam",
        nationality="Vietnam",
        issued_date="2021-01-01",
        expired_date="2031-01-01",
    )
    db.add(verified_identity)
    db.commit()

    def _fake_decrypt_document_payload(payload: str | None) -> dict | None:
        if payload == "identity-envelope":
            return {"identity_number": "123456789012"}
        if payload == "document-envelope":
            return {
                "parsed_fields": {
                    "id_number": "123456789012",
                    "full_name": "Nguyen Van A",
                    "place_of_origin": "Thanh, Kim Dong, Hung Yen",
                    "place_of_residence": "Long Bien, Ha Noi",
                    "issue_place": "Cuc Canh Sat",
                }
            }
        return None

    monkeypatch.setattr(
        ekyc_requests,
        "decrypt_document_payload",
        _fake_decrypt_document_payload,
    )

    response = client.get(
        f"{settings.API_V1_STR}/ekyc/requests/me/identity",
        headers=user_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["is_verified"] is True
    assert payload["identity_number"] == "********9012"
    assert payload["full_name"] == "Nguyen Van A"
    assert payload["birth_date"] == "1999-01-01"
    assert payload["gender"] == "Nam"
    assert payload["nationality"] == "Vietnam"
    assert payload["address"] == "Long Bien, Ha Noi"
    assert payload["place_of_origin"] == "Thanh, Kim Dong, Hung Yen"
    assert payload["place_of_residence"] == "Long Bien, Ha Noi"
    assert payload["issued_date"] == "2021-01-01"
    assert payload["issue_place"] == "Cuc Canh Sat"
    assert payload["expired_date"] == "2031-01-01"
    assert payload["verified_at"] is not None

    reveal_response = client.get(
        f"{settings.API_V1_STR}/ekyc/requests/me/identity?reveal=true",
        headers=user_headers,
    )

    assert reveal_response.status_code == 200
    assert reveal_response.json()["identity_number"] == "123456789012"


def test_my_verified_identity_does_not_return_other_users_identity(
    client: TestClient,
    db: Session,
) -> None:
    owner = create_random_user(db)
    other_user = create_random_user(db)
    other_user_headers = authentication_token_from_email(
        client=client,
        email=other_user.email,
        db=db,
    )
    ekyc_session = EkycSession(
        user_id=owner.id,
        status=EkycRequestStatus.SUCCESS,
    )
    db.add(ekyc_session)
    db.commit()
    db.refresh(ekyc_session)

    ekyc_result = EkycResult(
        session_id=ekyc_session.id,
        user_id=owner.id,
        status=EkycRequestStatus.SUCCESS,
        decision="match",
    )
    db.add(ekyc_result)
    db.commit()
    db.refresh(ekyc_result)

    verified_identity = VerifiedIdentity(
        user_id=owner.id,
        ekyc_result_id=ekyc_result.id,
        identity_number_hash="other-user-id-hash",
        full_name="Owner Only",
    )
    db.add(verified_identity)
    db.commit()

    response = client.get(
        f"{settings.API_V1_STR}/ekyc/requests/me/identity",
        headers=other_user_headers,
    )

    assert response.status_code == 200
    assert response.json() == {
        "is_verified": False,
        "document_type": None,
        "identity_number": None,
        "full_name": None,
        "birth_date": None,
        "gender": None,
        "nationality": None,
        "address": None,
        "place_of_origin": None,
        "place_of_residence": None,
        "issued_date": None,
        "issue_place": None,
        "expired_date": None,
        "verified_at": None,
    }


def test_admin_detail_flags_duplicate_identity_number(
    client: TestClient,
    db: Session,
    superuser_token_headers: dict[str, str],
) -> None:
    existing_user = create_random_user(db)
    reviewer_target_user = create_random_user(db)
    duplicate_number = "123456789012"

    existing_session = EkycSession(
        user_id=existing_user.id,
        status=EkycRequestStatus.SUCCESS,
        document_type="CCCD",
    )
    db.add(existing_session)
    db.commit()
    db.refresh(existing_session)

    existing_result = EkycResult(
        session_id=existing_session.id,
        user_id=existing_user.id,
        status=EkycRequestStatus.SUCCESS,
        decision="match",
        document_result={"parsed_fields": {"id_number": duplicate_number}},
    )
    db.add(existing_result)
    db.commit()
    db.refresh(existing_result)

    db.add(
        VerifiedIdentity(
            user_id=existing_user.id,
            ekyc_result_id=existing_result.id,
            identity_number_hash=ekyc_requests._identity_number_hash(duplicate_number),
            full_name="Existing User",
        )
    )
    db.commit()

    reviewing_session = EkycSession(
        user_id=reviewer_target_user.id,
        status=EkycRequestStatus.MANUAL_REVIEW,
        document_type="CCCD",
        result={"parsed_fields": {"id_number": duplicate_number}},
    )
    db.add(reviewing_session)
    db.commit()
    db.refresh(reviewing_session)

    response = client.get(
        f"{settings.API_V1_STR}/ekyc/requests/{reviewing_session.request_id}/admin-detail",
        headers=superuser_token_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["duplicate_identity_detected"] is True
    assert "Duplicate identity number detected." in payload["duplicate_identity_warning"]
    assert existing_user.email in payload["duplicate_identity_warning"]


def test_approve_ekyc_request_rejects_duplicate_active_identity(
    client: TestClient,
    db: Session,
    superuser_token_headers: dict[str, str],
) -> None:
    existing_user = create_random_user(db)
    target_user = create_random_user(db)
    duplicate_number = "123456789012"

    existing_session = EkycSession(
        user_id=existing_user.id,
        status=EkycRequestStatus.SUCCESS,
        document_type="CCCD",
    )
    db.add(existing_session)
    db.commit()
    db.refresh(existing_session)

    existing_result = EkycResult(
        session_id=existing_session.id,
        user_id=existing_user.id,
        status=EkycRequestStatus.SUCCESS,
        decision="match",
        document_result={"parsed_fields": {"id_number": duplicate_number}},
    )
    db.add(existing_result)
    db.commit()
    db.refresh(existing_result)

    db.add(
        VerifiedIdentity(
            user_id=existing_user.id,
            ekyc_result_id=existing_result.id,
            identity_number_hash=ekyc_requests._identity_number_hash(duplicate_number),
        )
    )
    db.commit()

    target_session = EkycSession(
        user_id=target_user.id,
        status=EkycRequestStatus.MANUAL_REVIEW,
        document_type="CCCD",
        result={"parsed_fields": {"id_number": duplicate_number}},
    )
    db.add(target_session)
    db.commit()
    db.refresh(target_session)

    target_result = EkycResult(
        session_id=target_session.id,
        user_id=target_user.id,
        status=EkycRequestStatus.MANUAL_REVIEW,
        decision="consider",
        document_result={"parsed_fields": {"id_number": duplicate_number}},
    )
    db.add(target_result)
    db.commit()

    response = client.post(
        f"{settings.API_V1_STR}/ekyc/requests/{target_session.request_id}/approve",
        headers=superuser_token_headers,
        json={},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Cannot approve because this identity number is already verified "
        f"for account {existing_user.email}."
    )
