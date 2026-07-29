"""Deterministic extraction from YOLO layout OCR blocks — authoritative for all fields."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from ekyc_document.parser import (
    _normalize_ascii,
    _clean_cccd_address,
    _correct_place_names,
    _correct_vietnamese_ocr,
    _find_date,
    _normalize_issue_place,
    _parse_mrz_expiry_date,
    cccd_id_matches_demographics,
)
from ekyc_document.schemas import ParsedFields

_DATE_FIELDS = frozenset({"date_of_birth", "issue_date", "expiry_date"})

# Fields managed exclusively via YOLO labeled blocks when layout pipeline is active.
_LAYOUT_MANAGED_FIELDS = frozenset(
    {
        "id_number",
        "full_name",
        "date_of_birth",
        "sex",
        "nationality",
        "place_of_origin",
        "place_of_residence",
        "issue_date",
        "issue_place",
        "expiry_date",
    }
)

# YOLO labeled block header → ParsedFields key (uppercase labels from yolo_layout_pipeline).
_LAYOUT_LABEL_TO_FIELD: dict[str, str] = {
    "ID_NUMBER": "id_number",
    "FULL_NAME": "full_name",
    "DATE_OF_BIRTH": "date_of_birth",
    "SEX": "sex",
    "GENDER": "sex",
    "NATIONALITY": "nationality",
    "PLACE_OF_ORIGIN": "place_of_origin",
    "BIRTHPLACE": "place_of_origin",
    "PLACE_OF_RESIDENCE": "place_of_residence",
    "ADDRESS": "place_of_residence",
    "ISSUE_DATE": "issue_date",
    "ISSUE_PLACE": "issue_place",
    "EXPIRY_DATE": "expiry_date",
    "EXPIRY": "expiry_date",
}

_LAYOUT_BLOCK_HEADER = re.compile(r"^\[([A-Z][A-Z0-9_]*)\]\s*$", re.MULTILINE)

_OCR_DATE_DIGIT_FIX = str.maketrans(
    {
        "O": "0",
        "o": "0",
        "D": "0",
        "Q": "0",
        "I": "1",
        "l": "1",
        "|": "1",
        "S": "5",
        "B": "8",
        "Z": "2",
    }
)

_DATE_RE = re.compile(r"(?<!\d)(\d{2})[/.\-](\d{2})[/.\-](\d{4})(?!\d)")

_FIELD_LABEL_ALIASES: dict[str, tuple[str, ...]] = {
    "id_number": ("SO", "NO", "NO.", "ID", "ID NUMBER"),
    "full_name": ("HO VA TEN", "HO TEN", "FULL NAME"),
    "date_of_birth": ("NGAY SINH", "DATE OF BIRTH"),
    "sex": ("GIOI TINH", "SEX"),
    "nationality": (
        "QUOC TICH",
        "QUC TICH",
        "NATIONALITY",
        "NATIONELITY",
        "NALIUNALITY",
        "NALIONALITY",
    ),
    "place_of_origin": ("QUE QUAN", "PLACE OF ORIGIN", "PLACE OF ONIGIN"),
    "place_of_residence": (
        "NOI THUONG TRU",
        "NOI THUNG TRU",
        "PLACE OF RESIDENCE",
        "PLACS OF RESIDENCE",
    ),
    "issue_date": ("NGAY CAP", "DATE OF ISSUE"),
    "issue_place": ("NOI CAP", "PLACE OF ISSUE", "ISSUING AUTHORITY", "ISSUED BY"),
    "expiry_date": ("CO GIA TRI DEN", "HET HAN", "DATE OF EXPIRY"),
}

_FIELD_VALUE_PATTERNS: dict[str, tuple[str, ...]] = {
    "id_number": (
        r"(?is)^(?:.*(?:s[oố]\s*/?\s*no\.?|no\.?|id\s*number))\s*[:;.\-/|I]*\s*(.+)$",
    ),
    "full_name": (
        r"(?is)^(?:.*(?:h[oọ]\s*v[aà]\s*t[eê]n|ho\s*va\s*ten|h[oọ]\s*t[eê]n|full\s*name))\s*[:;.\-/|I]*\s*(.+)$",
    ),
    "sex": (
        r"(?is)^(?:.*(?:gi[oớ]i\s*t[ií]nh|gioi\s*tinh|sex))\s*[:;.\-/|I]*\s*(.+)$",
    ),
    "nationality": (
        r"(?is)^(?:.*(?:qu[oốôó]c?\s*t[iị]ch|quc\s*tich|nationality|nationelity|naliunality|nalionality))\s*[:;.\-/|I]*\s*(.+)$",
    ),
    "place_of_origin": (
        r"(?is)^(?:.*(?:qu[eê]\s*qu[aá]n|que\s*quan|place\s*of\s*o[nr]?igin))\s*[:;.\-/|I]*\s*(.+)$",
    ),
    "place_of_residence": (
        r"(?is)^(?:.*(?:n[oơ]i\s*th[ưuoòờ]ng\s*tr[uú]|noi\s*thuong\s*tru|noi\s*thung\s*tru|place\s*of\s*residen[a-z]*|placs\s*of\s*residen[a-z]*))\s*[:;.\-/|I]*\s*(.+)$",
    ),
    "issue_place": (
        r"(?is)^(?:.*(?:n[oơ]i\s*c[aấ]p|noi\s*cap|place\s*of\s*issue|issuing\s*authority|issued\s*by))\s*[:;.\-/|I]*\s*(.+)$",
    ),
}


def has_labeled_layout_blocks(raw_text: str) -> bool:
    return bool(_LAYOUT_BLOCK_HEADER.search(raw_text or ""))


def _line_is_only_layout_label(line: str, field_name: str) -> bool:
    aliases = _FIELD_LABEL_ALIASES.get(field_name, ())
    if not aliases:
        return False
    ascii_line = _normalize_ascii(line).strip(" :;./-|I")
    if not ascii_line:
        return True
    return any(alias in ascii_line for alias in aliases) and len(ascii_line) <= 32


def _strip_layout_value_label(text: str, field_name: str) -> str:
    """Remove Vietnamese/English printed field labels from a YOLO crop value."""
    cleaned_lines: list[str] = []
    for raw_line in (text or "").splitlines():
        line = raw_line.strip(" \t")
        if not line:
            continue

        stripped = line
        for pattern in _FIELD_VALUE_PATTERNS.get(field_name, ()):
            match = re.match(pattern, line)
            if match:
                stripped = match.group(1).strip(" :;./-|I")
                break

        if not stripped or _line_is_only_layout_label(stripped, field_name):
            continue
        cleaned_lines.append(stripped)

    return "\n".join(cleaned_lines).strip()


def _split_layout_blocks(raw_text: str) -> list[tuple[str, str]]:
    """Return [(LABEL, content), ...] from [LABEL]\\n... blocks."""
    text = raw_text.strip()
    if not text:
        return []

    matches = list(_LAYOUT_BLOCK_HEADER.finditer(text))
    if not matches:
        return []

    blocks: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        label = match.group(1).upper()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        content = text[start:end].strip()
        blocks.append((label, content))
    return blocks


def _normalize_date_string(day: str, month: str, year: str) -> str | None:
    try:
        dt = datetime(int(year), int(month), int(day))
    except ValueError:
        return None
    if dt.year < 1900 or dt.year > 2100:
        return None
    return f"{day.zfill(2)}/{month.zfill(2)}/{year}"


def extract_layout_date(text: str) -> str | None:
    """Extract DD/MM/YYYY from a YOLO field crop, fixing common OCR digit errors."""
    if not text or not text.strip():
        return None

    cleaned = text.translate(_OCR_DATE_DIGIT_FIX)
    cleaned = re.sub(r"(?i)(?<=\D)o(?=\d)", "0", cleaned)

    # Prefer date after Vietnamese/English label on same block.
    for label_pattern in (
        r"(?i)(?:ngày\s*sinh|ngay\s*sinh|date\s*of\s*birth)\s*[/:\-]?\s*",
        r"(?i)(?:ngày\s*cấp|ngay\s*cap|date\s*of\s*issue)\s*[/:\-]?\s*",
        r"(?i)(?:có\s*giá\s*trị\s*đến|co\s*gia\s*tri\s*den|hết\s*hạn|het\s*han|date\s*of\s*expiry)\s*[/:\-]?\s*",
    ):
        match = re.search(label_pattern + r"(\d{2})[/.\-](\d{2})[/.\-](\d{4})", cleaned)
        if match:
            normalized = _normalize_date_string(match.group(1), match.group(2), match.group(3))
            if normalized:
                return normalized

    match = _DATE_RE.search(cleaned)
    if not match:
        legacy = _find_date(cleaned)
        return legacy.replace("-", "/").replace(".", "/") if legacy else None

    return _normalize_date_string(match.group(1), match.group(2), match.group(3))


def _extract_layout_id_number(text: str) -> str | None:
    value = _strip_layout_value_label(text, "id_number") or text
    cleaned = value.translate(_OCR_DATE_DIGIT_FIX)
    compact = re.sub(r"\D", "", cleaned)
    for candidate in re.findall(r"\d{12}", compact):
        if candidate.startswith("0") or candidate[0] in "0123456789":
            return candidate
    match = re.search(r"\b(\d{12})\b", cleaned)
    return match.group(1) if match else None


def _extract_layout_sex(text: str) -> str | None:
    value = _strip_layout_value_label(text, "sex") or text
    lower = value.lower()
    if re.search(r"\b(nữ|nu|female|^\s*n\s*$)\b", lower):
        return "Nữ"
    if re.search(r"\b(nam|male|^\s*m\s*$)\b", lower):
        return "Nam"
    return None


def _extract_layout_text_field(
    text: str,
    *,
    field_name: str,
    is_address: bool = False,
) -> str | None:
    value = _strip_layout_value_label(text, field_name) or text.strip()
    if not value:
        return None
    # Drop embedded dates/labels from noisy OCR inside name/address crops.
    value = re.sub(
        r"(?i)(ngày\s*sinh|ngay\s*sinh|date\s*of\s*birth|giới\s*tính|gioi\s*tinh|sex|quốc\s*tịch|quoc\s*tich).*",
        "",
        value,
    ).strip(" ,;:-/")
    if not value:
        return None
    if is_address:
        cleaned = _clean_cccd_address(value)
        return _correct_place_names(cleaned) if cleaned else None
    corrected = _correct_vietnamese_ocr(value)
    return corrected.strip() if corrected else value.strip()


def _extract_field_from_block(label: str, content: str) -> str | None:
    field_name = _LAYOUT_LABEL_TO_FIELD.get(label)
    if not field_name:
        return None

    if field_name in _DATE_FIELDS:
        return extract_layout_date(content)
    if field_name == "id_number":
        return _extract_layout_id_number(content)
    if field_name == "sex":
        return _extract_layout_sex(content)
    if field_name == "issue_place":
        value = _strip_layout_value_label(content, field_name) or content.strip()
        corrected = _correct_vietnamese_ocr(value.strip()) or value.strip()
        return _normalize_issue_place(corrected) or corrected
    if field_name == "nationality":
        value = _strip_layout_value_label(content, field_name) or content.strip()
        corrected = _correct_vietnamese_ocr(value.strip()) or value.strip()
        if "VIET NAM" in _normalize_ascii(corrected):
            return "Việt Nam"
        return corrected
    if field_name in {"place_of_origin", "place_of_residence"}:
        return _extract_layout_text_field(content, field_name=field_name, is_address=True)
    if field_name == "full_name":
        return _extract_layout_text_field(content, field_name=field_name, is_address=False)
    return content.strip() or None


def parse_labeled_layout_fields(raw_text: str) -> tuple[ParsedFields, frozenset[str]]:
    """Parse [FIELD] blocks from YOLO layout OCR. Returns fields + locked field names."""
    blocks = _split_layout_blocks(raw_text)
    if not blocks:
        return ParsedFields(), frozenset()

    data: dict[str, str | None] = {}
    locked: set[str] = set()

    for label, content in blocks:
        if label == "MRZ":
            mrz_expiry = _parse_mrz_expiry_date(content)
            if mrz_expiry and not data.get("expiry_date"):
                data["expiry_date"] = mrz_expiry
                locked.add("expiry_date")
            continue

        field_name = _LAYOUT_LABEL_TO_FIELD.get(label)
        if not field_name or field_name == "mrz":
            continue

        value = _extract_field_from_block(label, content)
        if not value:
            continue

        data[field_name] = value
        locked.add(field_name)

    if data.get("id_number") and data.get("date_of_birth"):
        if not cccd_id_matches_demographics(
            data.get("id_number"),
            data.get("date_of_birth"),
            data.get("sex"),
        ):
            data.pop("id_number", None)
            locked.discard("id_number")

    return ParsedFields(**data), frozenset(locked)


def overlay_layout_fields(
    base: ParsedFields | None,
    layout: ParsedFields | None,
    *,
    side: str,
) -> ParsedFields:
    """Apply YOLO layout values; back side only supplies issue/expiry/MRZ fields."""
    if base is None and layout is None:
        return ParsedFields()
    if base is None:
        return layout or ParsedFields()
    if layout is None:
        return base

    merged = base.model_dump()
    layout_data = layout.model_dump(exclude={"extra"})

    back_only = {"issue_date", "issue_place"}
    front_allowed = {
        "id_number",
        "full_name",
        "date_of_birth",
        "sex",
        "nationality",
        "place_of_origin",
        "place_of_residence",
        "expiry_date",
    }

    for field_name, value in layout_data.items():
        if not value or field_name == "extra":
            continue
        if side == "back" and field_name not in back_only and field_name != "expiry_date":
            if field_name not in _DATE_FIELDS:
                continue
        if side == "front" and field_name in back_only:
            continue
        if side == "front" and field_name not in front_allowed:
            continue
        merged[field_name] = value

    extra = dict(base.extra)
    merged["extra"] = extra
    return ParsedFields(**merged)


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    match = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", value.strip())
    if not match:
        return None
    try:
        return datetime(int(match.group(3)), int(match.group(2)), int(match.group(1)))
    except ValueError:
        return None


def validate_date_triplet(fields: ParsedFields) -> list[str]:
    """Return warnings when date ordering looks wrong."""
    warnings: list[str] = []
    dob = _parse_date(fields.date_of_birth)
    issue = _parse_date(fields.issue_date)
    expiry = _parse_date(fields.expiry_date)

    if dob and issue and dob >= issue:
        warnings.append("Ngày sinh không thể sau hoặc bằng ngày cấp.")
    if issue and expiry and issue >= expiry:
        warnings.append("Ngày cấp không thể sau hoặc bằng ngày hết hạn.")
    if dob and expiry and dob >= expiry:
        warnings.append("Ngày sinh không thể sau hoặc bằng ngày hết hạn.")
    if dob:
        age_years = (datetime.now() - dob).days / 365.25
        if age_years < 0:
            warnings.append("Ngày sinh nằm trong tương lai.")
        elif age_years > 120:
            warnings.append("Ngày sinh có vẻ không hợp lý (tuổi > 120).")
    return warnings


def finalize_document_dates(fields: ParsedFields) -> ParsedFields:
    """Normalize date strings to DD/MM/YYYY."""
    data = fields.model_dump()
    for field_name in _DATE_FIELDS:
        value = data.get(field_name)
        if not value:
            continue
        normalized = extract_layout_date(str(value))
        if normalized:
            data[field_name] = normalized
    return ParsedFields(**data)


def merge_layout_extractions(
    rule_fields: ParsedFields,
    front_text: str,
    back_text: str = "",
) -> tuple[ParsedFields, frozenset[str]]:
    """Merge rule parser output with authoritative YOLO layout block extraction."""
    front_layout, front_locked = parse_labeled_layout_fields(front_text)
    back_layout, back_locked = parse_labeled_layout_fields(back_text)
    has_layout = has_labeled_layout_blocks(front_text) or has_labeled_layout_blocks(back_text)

    if has_layout:
        # YOLO labels are authoritative — build from layout blocks first, rule parser fills gaps only.
        merged = overlay_layout_fields(ParsedFields(), front_layout, side="front")
        merged = overlay_layout_fields(merged, back_layout, side="back")
        rule_data = rule_fields.model_dump(exclude={"extra"})
        merged_data = merged.model_dump(exclude={"extra"})
        for field_name in _LAYOUT_MANAGED_FIELDS:
            if not merged_data.get(field_name):
                fallback = rule_data.get(field_name)
                if fallback:
                    if field_name == "id_number" and merged_data.get("date_of_birth"):
                        if not cccd_id_matches_demographics(
                            str(fallback),
                            str(merged_data.get("date_of_birth") or ""),
                            str(merged_data.get("sex") or ""),
                        ):
                            continue
                    merged_data[field_name] = fallback
        merged = ParsedFields(**merged_data, extra=dict(rule_fields.extra))
    else:
        merged = overlay_layout_fields(rule_fields, front_layout, side="front")
        merged = overlay_layout_fields(merged, back_layout, side="back")

    merged = finalize_document_dates(merged)

    locked = set(front_locked) | set(back_locked)
    for field_name in _DATE_FIELDS:
        if getattr(merged, field_name):
            locked.add(field_name)

    extra = dict(merged.extra)
    extra["ocr_locked_fields"] = sorted(locked)
    extra["layout_pipeline_used"] = has_layout

    date_warnings = validate_date_triplet(merged)
    if date_warnings:
        extra["date_validation_warnings"] = date_warnings

    is_expired, expiry_warning, expiry_meta = evaluate_document_expiry(merged.expiry_date)
    extra.update(expiry_meta)
    if expiry_warning:
        extra["expiry_warning"] = expiry_warning

    merged = merged.model_copy(update={"extra": extra})
    return merged, frozenset(locked)


def evaluate_document_expiry(
    expiry_date: str | None,
    *,
    now: datetime | None = None,
) -> tuple[bool, str | None, dict[str, Any]]:
    """Compare expiry_date to real time. Returns (is_expired, warning, metadata)."""
    if not expiry_date:
        return False, None, {}

    parsed = _parse_date(expiry_date)
    if not parsed:
        return False, None, {}

    today = (now or datetime.now()).date()
    expiry_day = parsed.date()
    days_remaining = (expiry_day - today).days
    meta: dict[str, Any] = {
        "document_expired": days_remaining < 0,
        "days_until_expiry": days_remaining,
    }

    if days_remaining < 0:
        return (
            True,
            f"Giấy tờ đã hết hạn (ngày hết hạn: {expiry_date}).",
            meta,
        )
    if days_remaining == 0:
        return (
            False,
            f"Giấy tờ hết hạn vào hôm nay ({expiry_date}).",
            meta,
        )
    if days_remaining <= 30:
        return (
            False,
            f"Giấy tờ sắp hết hạn còn {days_remaining} ngày (ngày hết hạn: {expiry_date}).",
            meta,
        )
    return False, None, meta


def apply_document_status_checks(
    fields: ParsedFields | None,
    warnings: list[str],
) -> ParsedFields | None:
    """Attach expiry metadata and append human-readable warnings."""
    if fields is None:
        return None

    is_expired, expiry_warning, expiry_meta = evaluate_document_expiry(fields.expiry_date)
    extra = dict(fields.extra)
    extra.update(expiry_meta)
    if expiry_warning:
        extra["expiry_warning"] = expiry_warning
        if expiry_warning not in warnings:
            warnings.append(expiry_warning)

    for item in extra.get("date_validation_warnings") or []:
        if item not in warnings:
            warnings.append(str(item))

    return fields.model_copy(update={"extra": extra})


def get_ocr_locked_fields(fields: ParsedFields | None) -> frozenset[str]:
    """Return fields that must not be overridden by LLM (all YOLO layout extractions)."""
    if fields is None:
        return frozenset()
    raw = fields.extra.get("ocr_locked_fields")
    if raw:
        return frozenset(str(item) for item in raw)
    # Without layout metadata, still protect populated dates from LLM override.
    locked = {name for name in _DATE_FIELDS if getattr(fields, name)}
    return frozenset(locked)
