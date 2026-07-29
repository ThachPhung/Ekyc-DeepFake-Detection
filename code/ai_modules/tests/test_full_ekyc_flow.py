from api.main import _back_document_json, _overall_ekyc_decision
from ekyc_document.schemas import DocumentAnalysisResult, ParsedFields


def test_full_ekyc_fails_without_front_face():
    assert (
        _overall_ekyc_decision(
            front_face_detected=False,
            front_face_confident=False,
            video_decision="match",
        )
        == "failed"
    )


def test_full_ekyc_considers_when_front_face_not_confident():
    assert (
        _overall_ekyc_decision(
            front_face_detected=True,
            front_face_confident=False,
            video_decision="match",
        )
        == "consider"
    )


def test_full_ekyc_matches_when_front_face_and_video_match():
    assert (
        _overall_ekyc_decision(
            front_face_detected=True,
            front_face_confident=True,
            video_decision="match",
        )
        == "match"
    )


def test_back_document_json_only_returns_issue_date_and_issued_by():
    result = DocumentAnalysisResult(
        document_type="CCCD",
        ocr_confidence=0.8,
        image_quality_score=0.7,
        document_face_detected=False,
        parsed_fields=ParsedFields(
            id_number="SHOULD_NOT_APPEAR",
            date_of_birth="SHOULD_NOT_APPEAR",
            nationality="SHOULD_NOT_APPEAR",
            issue_date="29/09/2022",
            extra={"issued_by": "Cục Cảnh sát quản lý hành chính về trật tự xã hội"},
        ),
    )

    payload = _back_document_json(result)

    assert payload["parsed_fields"] == {
        "issue_date": "29/09/2022",
        "issued_by": "Cục Cảnh sát quản lý hành chính về trật tự xã hội",
    }
