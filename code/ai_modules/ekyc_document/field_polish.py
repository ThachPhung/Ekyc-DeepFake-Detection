"""Post-process extracted document fields for Vietnamese OCR/LLM noise."""

from __future__ import annotations

import re

from ekyc_document.layout_field_parse import finalize_document_dates
from ekyc_document.parser import (
    _ascii_normalize,
    _clean_cccd_address,
    _correct_place_names,
    _correct_vietnamese_ocr,
    _normalize_issue_place,
    cccd_id_matches_demographics,
    parse_mrz_id_numbers,
    parse_mrz_name_tokens,
)
from ekyc_document.schemas import ParsedFields

# Common CCCD name tokens (MRZ is diacritic-less) → canonical Vietnamese spelling.
_VIETNAMESE_NAME_TOKEN_CANONICAL: dict[str, str] = {
    "AN": "An",
    "ANH": "Anh",
    "BINH": "Bình",
    "DOAN": "Đoàn",
    "DUC": "Đức",
    "DUONG": "Dương",
    "GIANG": "Giang",
    "HA": "Hà",
    "HAI": "Hai",
    "HAN": "Hân",
    "HANH": "Hạnh",
    "HIEN": "Hiền",
    "HOA": "Hoa",
    "HOANG": "Hoàng",
    "HONG": "Hồng",
    "HUONG": "Hương",
    "HUY": "Huy",
    "KHANH": "Khánh",
    "LAN": "Lan",
    "LINH": "Linh",
    "LONG": "Long",
    "LUONG": "Lương",
    "MINH": "Minh",
    "NAM": "Nam",
    "NGO": "Ngô",
    "NGOC": "Ngọc",
    "NGUYEN": "Nguyễn",
    "NHUNG": "Nhung",
    "PHUONG": "Phương",
    "PHUNG": "Phùng",
    "QUOC": "Quốc",
    "QUYNH": "Quỳnh",
    "SON": "Sơn",
    "TAI": "Tài",
    "THACH": "Thạch",
    "THANH": "Thanh",
    "THAO": "Thảo",
    "THI": "Thị",
    "THU": "Thu",
    "THUY": "Thúy",
    "TRANG": "Trang",
    "TRAN": "Trần",
    "TRUNG": "Trung",
    "TU": "Tú",
    "TUNG": "Tùng",
    "VU": "Vũ",
    "VAN": "Văn",
    "VIET": "Việt",
    "VINH": "Vinh",
    "XUAN": "Xuân",
    "PHUC": "Phúc",
    "PHUOC": "Phước",
    "DINH": "Đình",
    "DAO": "Đào",
    "DANG": "Đăng",
    "BICH": "Bích",
    "CUONG": "Cường",
    "KHANG": "Khang",
    "KHOA": "Khoa",
    "LE": "Lê",
    "LY": "Lý",
    "MAI": "Mai",
    "MY": "Mỹ",
    "NHI": "Nhi",
    "PHAT": "Phát",
    "QUANG": "Quang",
    "QUYEN": "Quyền",
    "TAM": "Tâm",
    "TRUC": "Trúc",
    "TUYET": "Tuyết",
    "UYEN": "Uyên",
    "YEN": "Yên",
}


def _apply_name_token_diacritics(text: str) -> str:
    """Map từng token họ tên sang chính tả có dấu chuẩn (theo MRZ/OCR không dấu)."""
    words_out: list[str] = []
    for word in text.split():
        key = _ascii_normalize(word).upper().replace("'", "")
        canonical = _VIETNAMESE_NAME_TOKEN_CANONICAL.get(key)
        words_out.append(canonical if canonical else word)
    return " ".join(words_out)


def correct_full_name_from_mrz(
    full_name: str | None,
    back_raw_text: str,
) -> str | None:
    """Align OCR/LLM name with MRZ tokens and fix common diacritic mistakes."""
    if not full_name or not back_raw_text.strip():
        return full_name

    mrz_tokens = parse_mrz_name_tokens(back_raw_text)
    if not mrz_tokens:
        return full_name

    words = full_name.split()
    if len(words) != len(mrz_tokens):
        return full_name

    corrected_words: list[str] = []
    for word, token in zip(words, mrz_tokens):
        word_ascii = _ascii_normalize(word).upper().replace(" ", "")
        if word_ascii != token:
            return full_name
        canonical = _VIETNAMESE_NAME_TOKEN_CANONICAL.get(token)
        corrected_words.append(canonical if canonical else word)

    corrected = " ".join(corrected_words)
    return corrected if corrected != full_name else full_name


def apply_mrz_name_correction(
    fields: ParsedFields | None,
    back_raw_text: str,
) -> ParsedFields | None:
    if fields is None or not back_raw_text.strip():
        return fields

    corrected_name = correct_full_name_from_mrz(fields.full_name, back_raw_text)
    if corrected_name == fields.full_name:
        return fields

    data = fields.model_dump()
    data["full_name"] = corrected_name
    return ParsedFields(**data)


def _name_matches_mrz_tokens(full_name: str | None, back_raw_text: str) -> bool:
    if not full_name or not back_raw_text.strip():
        return False
    mrz_tokens = parse_mrz_name_tokens(back_raw_text)
    if not mrz_tokens:
        return False
    name_tokens = [_ascii_normalize(token).upper() for token in full_name.split()]
    return name_tokens == mrz_tokens


def correct_id_number_from_mrz(
    fields: ParsedFields | None,
    back_raw_text: str,
) -> ParsedFields | None:
    """Use MRZ/id_back to repair a front OCR ID that fails CCCD demographics."""
    if fields is None or not back_raw_text.strip():
        return fields

    candidates = parse_mrz_id_numbers(back_raw_text)
    if not candidates:
        return fields

    best = next(
        (
            candidate
            for candidate in candidates
            if cccd_id_matches_demographics(
                candidate,
                fields.date_of_birth,
                fields.sex,
            )
        ),
        candidates[0],
    )

    current = fields.id_number
    if current == best:
        return fields

    best_matches_demographics = cccd_id_matches_demographics(
        best,
        fields.date_of_birth,
        fields.sex,
    )
    current_matches_demographics = cccd_id_matches_demographics(
        current,
        fields.date_of_birth,
        fields.sex,
    )
    name_matches = _name_matches_mrz_tokens(fields.full_name, back_raw_text)

    should_replace = False
    if not current:
        should_replace = best_matches_demographics or name_matches
    elif best_matches_demographics and not current_matches_demographics:
        should_replace = True
    elif best_matches_demographics and name_matches and current not in candidates:
        should_replace = True

    if not should_replace:
        return fields

    data = fields.model_dump()
    data["id_number"] = best
    extra = dict(data.get("extra") or {})
    locked = {str(item) for item in extra.get("ocr_locked_fields") or []}
    locked.add("id_number")
    extra["ocr_locked_fields"] = sorted(locked)
    extra["id_number_corrected_from_mrz"] = True
    extra["id_number_source"] = "mrz"
    data["extra"] = extra
    return ParsedFields(**data)


def polish_extracted_fields(fields: ParsedFields | None) -> ParsedFields | None:
    if fields is None:
        return None

    data = fields.model_dump()
    data["full_name"] = _polish_full_name(data.get("full_name"))
    data["sex"] = _polish_sex(data.get("sex"))
    data["nationality"] = _polish_nationality(data.get("nationality"))
    data["place_of_origin"] = _polish_address(data.get("place_of_origin"))
    data["place_of_residence"] = _polish_address(data.get("place_of_residence"))
    data["issue_place"] = _polish_issue_place(data.get("issue_place"))
    polished = ParsedFields(**data)
    return finalize_document_dates(polished)


def _polish_full_name(value: str | None) -> str | None:
    if not value:
        return value

    text = value.strip()
    text = text.replace("'", "'").replace("`", "'").replace("'", "'")
    text = text.replace("LU'ONG", "LƯƠNG").replace("Lu'ong", "Lương")
    text = re.sub(r"(?i)phu'ong", "PHƯƠNG", text)
    text = re.sub(r"(?i)du'ong", "DƯƠNG", text)
    text = re.sub(r"(?i)lu'ong", "LƯƠNG", text)
    text = re.sub(r"(?i)u'o", "ƯƠ", text)
    text = re.sub(r"(?i)u'ong", "ƯƠNG", text)
    text = _correct_vietnamese_ocr(text) or text
    text = _apply_name_token_diacritics(text)

    if text.isupper() or all(part.isupper() for part in text.split()):
        normalized = text.upper().replace("QUÓC", "QUỐC")
        text = _title_case_vietnamese_name(normalized)
    return text.strip() or None


def _title_case_vietnamese_name(text: str) -> str:
    words: list[str] = []
    for word in text.split():
        lower = word.lower()
        if lower in {"và", "va", "thị", "thi", "đình", "dinh", "van", "văn"}:
            words.append(lower.capitalize() if lower == "và" else lower.title())
        else:
            words.append(word.capitalize())
    return " ".join(words)


def _polish_sex(value: str | None) -> str | None:
    if not value:
        return value
    text = value.strip()
    lower = text.lower()
    if lower in {"n", "nu", "nữ", "female", "f"}:
        return "Nữ"
    if lower.startswith("nam") or lower in {"m", "male"}:
        return "Nam"
    if lower.startswith("nữ") or "ữ" in text:
        return "Nữ"
    return text


def _polish_nationality(value: str | None) -> str | None:
    if not value:
        return value
    corrected = _correct_vietnamese_ocr(value.strip()) or value.strip()
    if corrected.lower().replace(" ", "") in {"vietnam", "vitnam", "việtnam"}:
        return "Việt Nam"
    return corrected


def _polish_address(value: str | None) -> str | None:
    if not value:
        return value

    cleaned = _clean_cccd_address(value)
    if not cleaned:
        return None
    corrected = _correct_place_names(cleaned) or cleaned
    deduped = _dedupe_address_parts(corrected)
    return deduped.strip() or None


def _dedupe_address_parts(value: str) -> str:
    parts = [part.strip(" ,") for part in re.split(r"\s*,\s*", value) if part.strip(" ,")]
    if not parts:
        return value

    kept: list[str] = []
    seen: set[str] = set()
    for part in parts:
        key = re.sub(r"\s+", " ", part).strip().lower()
        if key in seen:
            continue
        seen.add(key)
        kept.append(part)
    return ", ".join(kept)


def _polish_issue_place(value: str | None) -> str | None:
    if not value:
        return value
    corrected = _correct_vietnamese_ocr(value.strip()) or value.strip()
    normalized = _normalize_issue_place(corrected)
    return normalized or corrected
