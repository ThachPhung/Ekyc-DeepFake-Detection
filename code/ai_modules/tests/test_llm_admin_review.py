from __future__ import annotations

from unittest.mock import patch

from ekyc_document.llm_admin_review import (
    LLMAdminDecisionReviewer,
    build_admin_case_summary,
)
from ekyc_document.llm_extract import LLMCallResult, LLMTokenUsage


def test_build_admin_case_summary_from_unified_result() -> None:
    summary = build_admin_case_summary(
        unified_result={
            "decision": "consider",
            "score": 0.72,
            "front_document": {
                "parsed_fields": {"full_name": "Nguyễn Văn A", "id_number": "001234567890"},
                "ocr_confidence": 0.91,
            },
            "video": {
                "decision": "consider",
                "matching": {"similarity": 0.55, "decision": "consider"},
                "risk": {"score": 0.41, "reason_codes": ["face_match_review"]},
            },
        }
    )
    assert summary["overall_decision"] == "consider"
    assert summary["document"]["parsed_fields"]["full_name"] == "Nguyễn Văn A"
    assert summary["biometric"]["face_similarity"] == 0.55


def test_review_case_parses_new_llm_payload() -> None:
    fake_payload = {
        "ket_luan": "REVIEW",
        "muc_do_rui_ro": "TRUNG BÌNH",
        "do_tin_cay": 0.82,
        "tom_tat": "Cần review thủ công do face match vùng xám.",
        "diem_tich_cuc": ["Passive liveness đạt"],
        "van_de_phat_hien": ["Face similarity 0.55 thấp hơn ngưỡng"],
        "bang_chung": [
            {
                "hang_muc": "Face matching",
                "ket_qua": "Similarity 0.55",
                "do_tin_cay": 0.55,
            }
        ],
        "khuyen_nghi_cho_admin": "Yêu cầu admin xem lại video và ảnh CCCD.",
        "danh_sach_can_admin_kiem_tra": ["Đối chiếu khuôn mặt thủ công"],
        "du_lieu_con_thieu": ["Lipsync chưa chạy"],
        "giai_thich": "Điểm khớp khuôn mặt nằm ở vùng xám nên cần kiểm tra thêm.",
    }
    fake_call = LLMCallResult(
        payload=fake_payload,
        usage=LLMTokenUsage(stage="admin_review", provider="openai", model="gpt-test"),
    )

    with patch("ekyc_document.llm_admin_review.LLMFieldExtractor.is_ready", return_value=True), patch(
        "ekyc_document.llm_admin_review.LLMFieldExtractor.complete_json",
        return_value=fake_call,
    ):
        reviewer = LLMAdminDecisionReviewer()
        result = reviewer.review_case({"overall_decision": "consider"})

    assert result.ket_luan == "REVIEW"
    assert result.do_tin_cay == 0.82
    assert "review thủ công" in result.tom_tat
    assert result.bang_chung[0].hang_muc == "Face matching"
    assert result.du_lieu_con_thieu == ["Lipsync chưa chạy"]


def test_review_case_parses_legacy_llm_payload() -> None:
    fake_payload = {
        "recommendation": "manual_review",
        "confidence": 0.82,
        "summary_vi": "Cần review thủ công.",
        "key_findings": ["Face similarity 0.55"],
        "risk_flags": ["face_match_review"],
        "supporting_evidence": ["Passive liveness passed"],
        "suggested_admin_action": "Yêu cầu admin xem lại video.",
        "caveats": ["Lipsync chưa chạy"],
    }
    fake_call = LLMCallResult(
        payload=fake_payload,
        usage=LLMTokenUsage(stage="admin_review", provider="openai", model="gpt-test"),
    )

    with patch("ekyc_document.llm_admin_review.LLMFieldExtractor.is_ready", return_value=True), patch(
        "ekyc_document.llm_admin_review.LLMFieldExtractor.complete_json",
        return_value=fake_call,
    ):
        reviewer = LLMAdminDecisionReviewer()
        result = reviewer.review_case({"overall_decision": "consider"})

    assert result.ket_luan == "REVIEW"
    assert result.tom_tat == "Cần review thủ công."
    assert result.diem_tich_cuc == ["Face similarity 0.55"]
