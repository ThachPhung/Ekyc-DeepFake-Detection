"""LLM-assisted review summary for admin eKYC decision support."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field

from ekyc_document.config import PipelineConfig
from ekyc_document.llm_extract import LLMFieldExtractor

KetLuan = Literal["PASS", "REVIEW", "REJECT"]
MucDoRuiRo = Literal["THẤP", "TRUNG BÌNH", "CAO"]

_ADMIN_SYSTEM_PROMPT = """You are an AI eKYC Review Assistant.

Your role is to review the outputs produced by an electronic Know Your Customer (eKYC) verification pipeline and assist a human administrator in making the final verification decision.

You are NOT the final decision maker.

Your responsibility is to objectively review the evidence, identify potential risks, explain inconsistencies, summarize findings, and provide a recommendation for the administrator.

==================================================
OBJECTIVE
==================================================

Review all available verification results, including but not limited to:

- Document Detection
- OCR Results
- Face Detection
- Face Matching
- Face Liveness
- Anti-Spoofing
- Deepfake Detection
- Document Tampering Detection
- Image Quality Assessment
- Business Rule Validation
- Any additional AI model outputs

Evaluate all available evidence before making any recommendation.

Never ignore any provided information.

==================================================
GENERAL REVIEW PRINCIPLES
==================================================

1. Base every conclusion ONLY on the provided evidence.

2. Never invent, infer, or assume information that is not explicitly provided.

3. Never hallucinate.

4. Missing information is NOT positive evidence.

5. If information is missing, explicitly identify what is missing.

6. Every conclusion must be supported by one or more pieces of evidence.

7. If different models disagree, clearly explain the conflict.

8. Prioritize security over convenience.

9. When uncertainty exists, recommend manual review instead of making unsupported conclusions.

10. Never generate information outside the provided input.

==================================================
EVIDENCE POLICY
==================================================

Every conclusion MUST be traceable to the provided evidence.

Each recommendation must reference the evidence that supports it.

Do not provide generic explanations.

Incorrect:

"The image looks suspicious."

Correct:

"The blur score is high, which may reduce OCR reliability."

==================================================
CONFIDENCE POLICY
==================================================

Estimate confidence ONLY from the consistency and quality of the provided evidence.

Increase confidence when:

- Major verification modules consistently agree.
- No security risks are detected.
- Image quality is acceptable.
- OCR confidence is high.
- Face matching is strong.
- Liveness passes.

Decrease confidence when:

- Different models disagree.
- Required information is missing.
- OCR confidence is low.
- Image quality is poor.
- Warnings exist.
- Security models produce uncertain results.

Never fabricate confidence scores.

==================================================
CONFLICT RESOLUTION POLICY
==================================================

When verification modules disagree:

1. Explicitly describe the conflict.

2. Explain which evidence has higher priority.

3. Never ignore conflicting evidence.

4. If the conflict cannot be resolved confidently, recommend REVIEW.

==================================================
SECURITY PRIORITY
==================================================

Always evaluate findings using the following priority order:

1. Spoof Detection
2. Deepfake Detection
3. Document Tampering
4. Face Matching
5. Liveness
6. OCR
7. Image Quality
8. Business Rules

Higher-priority failures override lower-priority successes.

Example:

Face Matching: PASS

Spoof Detection: FAIL

Final Recommendation:

REJECT

==================================================
DECISION POLICY
==================================================

Recommend PASS only when ALL critical conditions are satisfied:

- No spoof detected.
- No deepfake detected.
- No document tampering.
- Face matching passes policy.
- Liveness passes policy.
- OCR passes policy.
- Business rules pass.
- No critical warning exists.
- Available evidence is consistent.

--------------------------------------------------

Recommend REVIEW when ANY of the following exists:

- Moderate OCR confidence.
- Borderline face similarity.
- Moderate image quality.
- Minor warnings.
- Missing information.
- Inconsistent model outputs.
- Uncertain evidence.

--------------------------------------------------

Recommend REJECT immediately when ANY critical condition exists:

- Spoof detected.
- Deepfake detected.
- Serious document tampering.
- Face similarity below policy threshold.
- Mandatory information missing.
- Critical OCR failure.
- Serious business rule violation.
- Security policy violation.

==================================================
MISSING DATA POLICY
==================================================

Missing data must NEVER be interpreted as a successful verification.

List every missing field.

Reduce confidence accordingly.

==================================================
EXPLAINABILITY POLICY
==================================================

Every recommendation must explain:

- What evidence supports the conclusion.
- Why risks exist.
- Why the recommendation is appropriate.

Do not produce vague explanations.

==================================================
HALLUCINATION POLICY
==================================================

Never create facts.

Never estimate values that are not provided.

Never fabricate identity information.

Never modify OCR values.

Never guess missing fields.

If evidence is insufficient, explicitly state that the evidence is insufficient.

==================================================
OUTPUT POLICY
==================================================

Return ONLY valid JSON.

Do not output Markdown.

Do not output code blocks.

Do not output explanations outside JSON.

Do not rename JSON fields.

Do not omit any JSON field.

Use empty arrays [] or empty strings "" when necessary.

==================================================
LANGUAGE POLICY
==================================================

The entire response MUST be written in Vietnamese.

All summaries, explanations, recommendations, evidence descriptions, and findings MUST use professional Vietnamese.

Do NOT output English except for the following values:

PASS
REVIEW
REJECT

==================================================
FINAL JSON SCHEMA
==================================================

{
  "ket_luan": "PASS | REVIEW | REJECT",

  "muc_do_rui_ro": "THẤP | TRUNG BÌNH | CAO",

  "do_tin_cay": 0.95,

  "tom_tat": "",

  "diem_tich_cuc": [],

  "van_de_phat_hien": [],

  "bang_chung": [
    {
      "hang_muc": "",
      "ket_qua": "",
      "do_tin_cay": 0.98
    }
  ],

  "khuyen_nghi_cho_admin": "",

  "danh_sach_can_admin_kiem_tra": [],

  "du_lieu_con_thieu": [],

  "giai_thich": ""
}

==================================================
FINAL INSTRUCTIONS
==================================================

Before generating the final recommendation:

1. Review every provided module.

2. Check for missing information.

3. Check for conflicting evidence.

4. Apply the security priority policy.

5. Apply the decision policy.

6. Ensure every conclusion is evidence-based.

7. Ensure the JSON is valid.

8. Ensure every explanation is written in Vietnamese.

9. If uncertainty remains, prefer REVIEW instead of PASS.

10. Never approve when the available evidence is insufficient.
"""


class BangChungItem(BaseModel):
    hang_muc: str = ""
    ket_qua: str = ""
    do_tin_cay: float = Field(default=0.0, ge=0.0, le=1.0)


class AdminLLMReviewResult(BaseModel):
    ket_luan: KetLuan = "REVIEW"
    muc_do_rui_ro: MucDoRuiRo = "TRUNG BÌNH"
    do_tin_cay: float = Field(default=0.5, ge=0.0, le=1.0)
    tom_tat: str = ""
    diem_tich_cuc: list[str] = Field(default_factory=list)
    van_de_phat_hien: list[str] = Field(default_factory=list)
    bang_chung: list[BangChungItem] = Field(default_factory=list)
    khuyen_nghi_cho_admin: str = ""
    danh_sach_can_admin_kiem_tra: list[str] = Field(default_factory=list)
    du_lieu_con_thieu: list[str] = Field(default_factory=list)
    giai_thich: str = ""
    provider: str | None = None
    model: str | None = None
    error: str | None = None
    ready: bool = True


@dataclass
class LLMAdminDecisionReviewer:
    config: PipelineConfig | None = None

    def __post_init__(self) -> None:
        if self.config is None:
            self.config = PipelineConfig()
        self._extractor = LLMFieldExtractor(self.config)

    def is_ready(self) -> bool:
        if not self.config.llm_admin_review_enabled:
            return False
        return self._extractor.is_ready()

    def diagnostics(self) -> dict[str, object]:
        return {
            "enabled": self.config.llm_admin_review_enabled,
            "auto": self.config.llm_admin_review_auto,
            "ready": self.is_ready(),
            "provider": self._extractor.config.llm_provider,
            "model": self._extractor.active_model,
        }

    def review_unified_result(self, unified_result: dict[str, Any]) -> AdminLLMReviewResult:
        case = build_admin_case_summary(unified_result=unified_result)
        return self.review_case(case)

    def review_case(self, case_summary: dict[str, Any]) -> AdminLLMReviewResult:
        if not self.config.llm_admin_review_enabled:
            return AdminLLMReviewResult(
                ket_luan="REVIEW",
                tom_tat="LLM admin review đang tắt (EKYC_LLM_ADMIN_REVIEW=false).",
                khuyen_nghi_cho_admin="Bật EKYC_LLM_ADMIN_REVIEW hoặc phân tích thủ công.",
                ready=False,
                error="disabled",
            )
        if not self._extractor.is_ready():
            return AdminLLMReviewResult(
                ket_luan="REVIEW",
                tom_tat="LLM chưa sẵn sàng — kiểm tra API key và EKYC_LLM_PROVIDER.",
                khuyen_nghi_cho_admin="Kiểm tra cấu hình LLM trước khi dùng gợi ý AI.",
                ready=False,
                error="llm_not_ready",
            )

        user_prompt = (
            "Dữ liệu hồ sơ eKYC (JSON):\n"
            f"{json.dumps(case_summary, ensure_ascii=False, indent=2)}\n\n"
            "Phân tích toàn bộ bằng chứng theo chính sách đã mô tả và trả JSON đúng schema."
        )
        try:
            call = self._extractor.complete_json(
                system_prompt=_ADMIN_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                stage="admin_review",
            )
            payload = _parse_admin_review_payload(call.payload)
            payload.provider = self._extractor.config.llm_provider
            payload.model = self._extractor.active_model
            payload.ready = True
            return payload
        except Exception as exc:  # noqa: BLE001
            return AdminLLMReviewResult(
                ket_luan="REVIEW",
                tom_tat=f"Không gọi được LLM: {exc}",
                khuyen_nghi_cho_admin="Thử lại hoặc phân tích thủ công.",
                ready=False,
                error=str(exc),
                provider=self._extractor.config.llm_provider,
                model=self._extractor.active_model,
            )


def build_admin_case_summary(
    *,
    unified_result: dict[str, Any] | None = None,
    request_id: str | None = None,
    status: str | None = None,
    decision: str | None = None,
    score: float | None = None,
    confidence: float | None = None,
    ocr_result: dict[str, Any] | None = None,
    video_result: dict[str, Any] | None = None,
    voice_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a compact, PII-aware case file for LLM admin review."""
    if unified_result:
        request_id = request_id or unified_result.get("request_id")
        status = status or unified_result.get("status")
        decision = decision or unified_result.get("decision")
        score = score if score is not None else unified_result.get("score")
        confidence = confidence if confidence is not None else unified_result.get("confidence")
        ocr_result = ocr_result or unified_result.get("front_document")
        video_result = video_result or unified_result.get("video")
        voice_result = voice_result or unified_result.get("voice")

    doc = ocr_result if isinstance(ocr_result, dict) else {}
    video = video_result if isinstance(video_result, dict) else {}
    voice = voice_result if isinstance(voice_result, dict) else {}
    parsed = doc.get("parsed_fields") if isinstance(doc.get("parsed_fields"), dict) else {}
    risk = video.get("risk") if isinstance(video.get("risk"), dict) else {}
    matching = video.get("matching") if isinstance(video.get("matching"), dict) else {}
    passive = video.get("passive_liveness") if isinstance(video.get("passive_liveness"), dict) else {}
    lipsync = risk.get("lipsync") if isinstance(risk.get("lipsync"), dict) else None

    return {
        "request_id": request_id,
        "pipeline_status": status,
        "overall_decision": decision,
        "aggregate_score": score,
        "aggregate_confidence": confidence,
        "document": {
            "document_type": doc.get("document_type"),
            "ocr_confidence": doc.get("ocr_confidence"),
            "image_quality_score": doc.get("image_quality_score"),
            "document_face_detected": doc.get("document_face_detected"),
            "document_face_confident": doc.get("document_face_confident"),
            "parsed_fields": {
                key: parsed.get(key)
                for key in (
                    "id_number",
                    "full_name",
                    "date_of_birth",
                    "sex",
                    "place_of_origin",
                    "place_of_residence",
                    "issue_date",
                    "expiry_date",
                )
            },
            "warnings": (doc.get("warnings") or [])[:8],
        },
        "biometric": {
            "video_decision": video.get("decision"),
            "face_similarity": matching.get("similarity"),
            "face_match_decision": matching.get("decision"),
            "passive_liveness_score": passive.get("score"),
            "passive_liveness_passed": passive.get("passed"),
            "active_liveness": video.get("active_liveness"),
            "quality_score": video.get("quality_score"),
            "decision_reasons": video.get("decision_reasons"),
        },
        "risk": {
            "score": risk.get("score"),
            "decision": risk.get("decision"),
            "reason_codes": risk.get("reason_codes"),
            "top_reasons": risk.get("top_reasons"),
            "evidence": _compact_risk_evidence(risk.get("evidence")),
            "lipsync": lipsync,
        },
        "voice": {
            "decision": voice.get("decision"),
            "wer": voice.get("wer"),
            "passed": voice.get("passed"),
        }
        if voice
        else None,
        "pipeline_warnings": (unified_result or {}).get("warnings", [])[:10]
        if unified_result
        else [],
    }


def _compact_risk_evidence(raw: object) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    compact: list[dict[str, Any]] = []
    for item in raw[:12]:
        if not isinstance(item, dict):
            continue
        compact.append(
            {
                "signal": item.get("signal"),
                "score": item.get("score"),
                "triggered": item.get("triggered"),
                "reason_code": item.get("reason_code"),
            }
        )
    return compact


def _parse_ket_luan(raw: object) -> KetLuan:
    value = str(raw or "REVIEW").upper().strip()
    if value in {"PASS", "REVIEW", "REJECT"}:
        return value  # type: ignore[return-value]
    legacy = str(raw or "").lower().strip()
    if legacy == "approve":
        return "PASS"
    if legacy == "reject":
        return "REJECT"
    return "REVIEW"


def _parse_muc_do_rui_ro(raw: object) -> MucDoRuiRo:
    value = str(raw or "TRUNG BÌNH").upper().strip()
    if value in {"THẤP", "TRUNG BÌNH", "CAO"}:
        return value  # type: ignore[return-value]
    return "TRUNG BÌNH"


def _parse_confidence(raw: object, *, default: float = 0.5) -> float:
    try:
        confidence = float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        confidence = default
    return max(0.0, min(1.0, confidence))


def _str_list(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [str(item).strip() for item in raw if str(item).strip()]


def _parse_bang_chung(raw: object) -> list[BangChungItem]:
    if not isinstance(raw, list):
        return []
    items: list[BangChungItem] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        items.append(
            BangChungItem(
                hang_muc=str(entry.get("hang_muc") or "").strip(),
                ket_qua=str(entry.get("ket_qua") or "").strip(),
                do_tin_cay=_parse_confidence(entry.get("do_tin_cay"), default=0.0),
            )
        )
    return items


def _parse_admin_review_payload(payload: dict[str, Any]) -> AdminLLMReviewResult:
    if "ket_luan" in payload or "tom_tat" in payload:
        return AdminLLMReviewResult(
            ket_luan=_parse_ket_luan(payload.get("ket_luan")),
            muc_do_rui_ro=_parse_muc_do_rui_ro(payload.get("muc_do_rui_ro")),
            do_tin_cay=_parse_confidence(payload.get("do_tin_cay")),
            tom_tat=str(payload.get("tom_tat") or "").strip(),
            diem_tich_cuc=_str_list(payload.get("diem_tich_cuc")),
            van_de_phat_hien=_str_list(payload.get("van_de_phat_hien")),
            bang_chung=_parse_bang_chung(payload.get("bang_chung")),
            khuyen_nghi_cho_admin=str(payload.get("khuyen_nghi_cho_admin") or "").strip(),
            danh_sach_can_admin_kiem_tra=_str_list(payload.get("danh_sach_can_admin_kiem_tra")),
            du_lieu_con_thieu=_str_list(payload.get("du_lieu_con_thieu")),
            giai_thich=str(payload.get("giai_thich") or "").strip(),
        )

    # Backward compatibility with legacy schema (approve/reject/manual_review).
    ket_luan = _parse_ket_luan(payload.get("recommendation"))
    bang_chung = [
        BangChungItem(hang_muc="Bằng chứng", ket_qua=item, do_tin_cay=0.0)
        for item in _str_list(payload.get("supporting_evidence"))
    ]
    return AdminLLMReviewResult(
        ket_luan=ket_luan,
        muc_do_rui_ro="TRUNG BÌNH",
        do_tin_cay=_parse_confidence(payload.get("confidence")),
        tom_tat=str(payload.get("summary_vi") or "").strip(),
        diem_tich_cuc=_str_list(payload.get("key_findings")),
        van_de_phat_hien=_str_list(payload.get("risk_flags")),
        bang_chung=bang_chung,
        khuyen_nghi_cho_admin=str(payload.get("suggested_admin_action") or "").strip(),
        danh_sach_can_admin_kiem_tra=_str_list(payload.get("caveats")),
        du_lieu_con_thieu=[],
        giai_thich="",
    )
