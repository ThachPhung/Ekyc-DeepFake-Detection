"""Text normalization and scoring for Vietnamese speech verification."""

from __future__ import annotations

import re
import unicodedata

from ekyc_document.schemas import DecisionType

_VIETNAMESE_DIGITS = {
    "0": "không",
    "1": "một",
    "2": "hai",
    "3": "ba",
    "4": "bốn",
    "5": "năm",
    "6": "sáu",
    "7": "bảy",
    "8": "tám",
    "9": "chín",
}

_CHALLENGE_TEMPLATES = (
    "Tôi xác nhận danh tính của mình",
    "Tôi đồng ý xác minh danh tính hôm nay",
    "Tôi cam kết thông tin cung cấp là chính xác",
    "Tôi xác nhận đây là khuôn mặt thật của tôi",
    "Tôi đồng ý thực hiện xác thực sinh trắc học",
)

VOICE_CHALLENGE_CODE_DIGITS = 8


def normalize_vietnamese_text(text: str) -> str:
    if not text:
        return ""
    normalized = unicodedata.normalize("NFD", text.lower())
    without_marks = "".join(
        char for char in normalized if unicodedata.category(char) != "Mn"
    )
    cleaned = re.sub(r"[^a-z0-9\s]", " ", without_marks)
    return " ".join(cleaned.split())


def digits_to_vietnamese_words(text: str) -> str:
    return "".join(_VIETNAMESE_DIGITS.get(char, char) for char in text)


def word_error_rate(reference: str, hypothesis: str) -> float:
    ref_words = reference.split()
    hyp_words = hypothesis.split()
    if not ref_words:
        return 1.0 if hyp_words else 0.0
    if not hyp_words:
        return 1.0

    rows = len(ref_words) + 1
    cols = len(hyp_words) + 1
    matrix = [[0] * cols for _ in range(rows)]
    for row in range(rows):
        matrix[row][0] = row
    for col in range(cols):
        matrix[0][col] = col

    for row in range(1, rows):
        for col in range(1, cols):
            cost = 0 if ref_words[row - 1] == hyp_words[col - 1] else 1
            matrix[row][col] = min(
                matrix[row - 1][col] + 1,
                matrix[row][col - 1] + 1,
                matrix[row - 1][col - 1] + cost,
            )
    return round(matrix[rows - 1][cols - 1] / len(ref_words), 4)


def token_overlap_similarity(reference: str, hypothesis: str) -> float:
    ref_tokens = set(reference.split())
    hyp_tokens = set(hypothesis.split())
    if not ref_tokens:
        return 0.0 if hyp_tokens else 1.0
    return round(len(ref_tokens & hyp_tokens) / len(ref_tokens), 4)


def voice_decision_from_wer(
    wer: float,
    *,
    pass_threshold: float,
    consider_threshold: float,
) -> DecisionType:
    if wer <= pass_threshold:
        return "match"
    if wer <= consider_threshold:
        return "consider"
    return "failed"


def challenge_templates() -> tuple[str, ...]:
    return _CHALLENGE_TEMPLATES
