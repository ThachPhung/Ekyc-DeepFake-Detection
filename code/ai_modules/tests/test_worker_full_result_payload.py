from worker import ekyc_worker


class _FakeDocumentResult:
    ocr_confidence = 0.9
    image_quality_score = 0.8
    document_face_detected = True
    document_face_confident = True
    warnings = []

    def to_full_json(self):
        return {
            "document_type": "CCCD",
            "parsed_fields": {
                "id_number": "001201123456",
                "full_name": "NGUYEN VAN A",
            },
        }


class _FakeMatching:
    similarity = 0.92


class _FakePassiveLiveness:
    score = 0.86


class _FakeVideoResult:
    decision = "match"
    quality_score = 0.84
    passive_liveness = _FakePassiveLiveness()
    matching = _FakeMatching()
    voice_verification = None
    warnings = []

    def model_dump(self, mode="python"):
        return {
            "decision": self.decision,
            "quality_score": self.quality_score,
            "mode": mode,
        }


class _FakeDocumentPipeline:
    def __init__(self, _config):
        pass

    def analyze_two_sides(self, *_args, **_kwargs):
        return _FakeDocumentResult()


class _FakeBiometricPipeline:
    def __init__(self, _config):
        pass

    def analyze_video(self, *_args, **_kwargs):
        return _FakeVideoResult()


def test_unified_result_payload_preserves_full_document_json() -> None:
    document_payload = {
        "document_type": "CCCD",
        "parsed_fields": {
            "id_number": "001201123456",
            "full_name": "NGUYEN VAN A",
        },
    }
    video_payload = {"decision": "match"}
    voice_payload = {"decision": "passed"}

    payload = ekyc_worker._build_unified_result_payload(
        decision="match",
        similarity=0.91,
        score=0.88,
        confidence=0.85,
        document_payload=document_payload,
        video_payload=video_payload,
        voice_payload=voice_payload,
        warnings=[],
    )

    assert payload["success"] is True
    assert payload["front_document"] == document_payload
    assert payload["front_document"]["parsed_fields"]["id_number"] == "001201123456"
    assert payload["video"] == video_payload
    assert payload["voice"] == voice_payload


def test_unified_success_sends_verified_email(monkeypatch, tmp_path) -> None:
    updates = []
    saved_results = []
    sent_emails = []
    front_path = tmp_path / "front.jpg"
    back_path = tmp_path / "back.jpg"
    liveness_path = tmp_path / "liveness.mp4"
    front_path.write_bytes(b"front")
    back_path.write_bytes(b"back")
    liveness_path.write_bytes(b"video")

    monkeypatch.setattr(ekyc_worker, "DocumentPipeline", _FakeDocumentPipeline)
    monkeypatch.setattr(ekyc_worker, "BiometricPipeline", _FakeBiometricPipeline)
    monkeypatch.setattr(
        ekyc_worker,
        "_update_unified_request",
        lambda **kwargs: updates.append(kwargs),
    )
    monkeypatch.setattr(
        ekyc_worker,
        "_save_ekyc_result",
        lambda **kwargs: saved_results.append(kwargs) or ("result-id", "user-id"),
    )
    monkeypatch.setattr(
        ekyc_worker,
        "_save_verified_identity",
        lambda **_kwargs: (True, "user@example.com", "Nguyen Van A"),
    )
    monkeypatch.setattr(
        ekyc_worker,
        "_send_ekyc_verified_email",
        lambda **kwargs: sent_emails.append(kwargs),
    )

    ekyc_worker._process_unified_job(
        {
            "request_id": "request-id",
            "front_image_path": str(front_path),
            "back_image_path": str(back_path),
            "liveness_path": str(liveness_path),
            "expected_text": "I confirm my identity",
            "document_type": "CCCD",
            "job_type": "EKYC_VERIFY_ALL",
        }
    )

    assert updates[-1]["status"] == "SUCCESS"
    assert saved_results[0]["status"] == "SUCCESS"
    assert sent_emails == [
        {"email_to": "user@example.com", "full_name": "Nguyen Van A"}
    ]
