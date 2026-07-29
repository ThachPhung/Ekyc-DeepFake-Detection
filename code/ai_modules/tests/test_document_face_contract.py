from ekyc_document.schemas import DocumentAnalysisResult, FaceResult, ParsedFields


def test_document_compact_payload_includes_face_confidence_flags():
    result = DocumentAnalysisResult(
        document_type="CCCD",
        ocr_confidence=0.91,
        image_quality_score=0.82,
        document_face_detected=True,
        document_face_confident=True,
        document_face_confidence=0.88,
        parsed_fields=ParsedFields(
            id_number="001201123456",
            full_name="NGUYEN VAN A",
            date_of_birth="01/01/2001",
        ),
        face=FaceResult(
            detected=True,
            bbox=[120, 80, 95, 120],
            confidence=0.93,
            quality_score=0.88,
            confident=True,
        ),
    )

    payload = result.to_backend_json()

    assert payload["document_face_detected"] is True
    assert payload["document_face_confident"] is True
    assert payload["document_face_confidence"] == 0.88
    assert payload["parsed_fields"]["id_number"] == "001201123456"
    assert payload["parsed_fields"]["full_name"] == "NGUYEN VAN A"
    assert payload["parsed_fields"]["field_presence"]["id_number"] is True


def test_document_full_payload_includes_face_quality_details():
    result = DocumentAnalysisResult(
        document_type="CCCD",
        ocr_confidence=0.91,
        image_quality_score=0.82,
        document_face_detected=True,
        document_face_confident=False,
        document_face_confidence=0.31,
        face=FaceResult(
            detected=True,
            bbox=[120, 80, 32, 38],
            confidence=0.58,
            quality_score=0.31,
            confident=False,
            warnings=["Ảnh chân dung trên giấy tờ bị mờ, cần chụp lại rõ nét hơn."],
        ),
    )

    payload = result.to_full_json()

    assert payload["document_face_confident"] is False
    assert payload["face"]["quality_score"] == 0.31
    assert payload["face"]["confident"] is False
    assert payload["face"]["warnings"]
