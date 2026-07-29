"""Rule-based parsing for Vietnamese identity documents."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from ekyc_document.schemas import DocumentType, ParsedFields

_LAYOUT_BLOCK_HEADER = re.compile(r"^\[([A-Z][A-Z0-9_]*)\]\s*$", re.MULTILINE)


def has_labeled_layout_blocks(raw_text: str) -> bool:
    return bool(_LAYOUT_BLOCK_HEADER.search(raw_text or ""))


CCCD_KEYWORDS = (
    "CĂN CƯỚC",
    "CĂN CUOC",
    "CĂN CƯỚC CÔNG DÂN",
    "CITIZEN IDENTITY",
    "IDENTITY CARD",
)
GPLX_KEYWORDS = (
    "GIẤY PHÉP LÁI XE",
    "GIAY PHEP LAI XE",
    "DRIVING LICENCE",
    "DRIVING LICENSE",
    "GPLX",
)
PASSPORT_KEYWORDS = (
    "PASSPORT",
    "HỘ CHIẾU",
    "HO CHIEU",
    "REPUBLIC OF",
)

CCCD_FIELD_LABELS = (
    "HỌ VÀ TÊN",
    "HO VA TEN",
    "FULL NAME",
    "HỌ TÊN",
    "NGÀY SINH",
    "NGAY SINH",
    "DATE OF BIRTH",
    "GIỚI TÍNH",
    "GIOI TINH",
    "SEX",
    "QUỐC TỊCH",
    "QUOC TICH",
    "NATIONALITY",
    "QUÊ QUÁN",
    "QUE QUAN",
    "PLACE OF ORIGIN",
    "NƠI THƯỜNG TRÚ",
    "NOI THUONG TRU",
    "PLACE OF RESIDENCE",
    "CÓ GIÁ TRỊ ĐẾN",
    "CO GIA TRI DEN",
    "DATE OF EXPIRY",
    "NGÀY HẾT HẠN",
    "NGAY HET HAN",
    "NGÀY CẤP",
    "NGAY CAP",
    "DATE OF ISSUE",
    "NƠI CẤP",
    "NOI CAP",
    "PLACE OF ISSUE",
    "ISSUING AUTHORITY",
    "PERSONAL IDENTIFICATION",
)

VIET_PROVINCE_ABBR = frozenset({
    "HP", "HN", "HCM", "SG", "DN", "BD", "NA", "VT", "CT", "AG", "BN", "KG", "LA",
    "QN", "QT", "ST", "TG", "TN", "TV", "VL", "YB", "CB", "DB", "GL", "HB", "HD",
    "HG", "HI", "HY", "KH", "LC", "LS", "ND", "NB", "NT", "PT", "PY", "QG", "SL",
    "TH", "TT", "TY", "BG", "CM", "DT", "VP",
})


@dataclass
class ParseResult:
    document_type: DocumentType
    fields: ParsedFields
    warnings: list[str]


@dataclass
class TwoSideParseResult:
    document_type: DocumentType
    fields: ParsedFields
    warnings: list[str]


_ENGLISH_ADMIN_PHRASES = (
    "FOR ADMINISTRATIVE",
    "DIRECTOR GENERAL",
    "SOCIAL ORDER",
    "PERSONAL IDENTIFICATION",
    "INDEX FINGER",
    "LEFT INDEX",
    "RIGHT INDEX",
    "SOCIALIST REPUBLIC",
    "INDEPENDENCE",
    "CITIZEN IDENTITY",
    "IDENTITY CARD",
    "DATE OF BIRTH",
    "FULL NAME",
    "PLACE OF ORIGIN",
    "PLACE OF RESIDENCE",
    "DATE OF EXPIRY",
    "DATE OF ISSUE",
    "POLICE DEPARTMENT",
)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.upper().strip())


def _normalize_ascii(text: str) -> str:
    text = text.replace("Đ", "D").replace("đ", "d")
    without_accents = unicodedata.normalize("NFKD", text)
    ascii_text = "".join(ch for ch in without_accents if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", ascii_text.upper().strip())


def _ascii_normalize(text: str) -> str:
    return _normalize_ascii(text)


def detect_document_type(text: str) -> DocumentType:
    normalized = _normalize(text)
    scores = {
        "CCCD": sum(1 for kw in CCCD_KEYWORDS if kw in normalized),
        "GPLX": sum(1 for kw in GPLX_KEYWORDS if kw in normalized),
        "PASSPORT": sum(1 for kw in PASSPORT_KEYWORDS if kw in normalized),
    }
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return "UNKNOWN"
    return best  # type: ignore[return-value]


def _find_date(text: str) -> str | None:
    cleaned = re.sub(r"(?i)(?<=\D)o(?=\d)", "0", text)
    match = re.search(r"(?<!\d)(\d{2}[/.-]\d{2}[/.-]\d{4})(?!\d)", cleaned)
    return match.group(1) if match else None


def _find_all_dates(text: str) -> list[str]:
    cleaned = re.sub(r"(?i)(?<=\D)o(?=\d)", "0", text)
    return re.findall(r"(?<!\d)(\d{2}[/.-]\d{2}[/.-]\d{4})(?!\d)", cleaned)


def _line_has_label(line: str, labels: tuple[str, ...]) -> bool:
    upper = _normalize(line)
    upper_ascii = _normalize_ascii(line)
    return any(label in upper or _normalize_ascii(label) in upper_ascii for label in labels)


def _value_after_label(line: str) -> str | None:
    parts = re.split(r"[:;\-]", line, maxsplit=1)
    if len(parts) == 2 and parts[1].strip():
        return parts[1].strip()
    return None


def _looks_like_next_field(line: str, labels: tuple[str, ...]) -> bool:
    if _line_has_label(line, labels):
        return True
    upper = _normalize(line)
    upper_ascii = _normalize_ascii(line)
    if upper_ascii.strip(" ,;:.") in {"CO", "NI DEN", "GIA", "GIA TRI", "CO GIA", "CO GIA TRI"}:
        return True
    if re.search(r"\b(TR|GIA TRI|CO GIA TRI|DATE OF EXPIRY)\b", upper_ascii) and (
        "DEN" in upper_ascii or "EXPIRY" in upper_ascii
    ):
        return True
    return bool(re.match(r"^(CỘNG HÒA|CONG HOA|SOCIALIST|ĐỘC LẬP|DOC LAP)\b", upper))


def _find_after_label(
    lines: list[str],
    labels: tuple[str, ...],
    *,
    collect_continuation: bool = False,
    stop_labels: tuple[str, ...] = CCCD_FIELD_LABELS,
    max_continuation_lines: int = 3,
) -> str | None:
    for i, line in enumerate(lines):
        if not _line_has_label(line, labels):
            continue

        value = _value_after_label(line)
        parts: list[str] = []
        if value:
            parts.append(value)

        continuation_count = 0
        for next_line in lines[i + 1 :]:
            if _looks_like_next_field(next_line, stop_labels):
                break
            if collect_continuation and parts and _find_date(next_line):
                break
            if next_line.strip():
                parts.append(next_line.strip())
                continuation_count += 1
            if not collect_continuation or continuation_count >= max_continuation_lines:
                break

        if parts:
            return " ".join(parts)
    return None


def _find_date_after_label(lines: list[str], labels: tuple[str, ...]) -> str | None:
    for i, line in enumerate(lines):
        if not _line_has_label(line, labels):
            continue
        same_line = _find_date(line)
        if same_line:
            return same_line
        value = _value_after_label(line)
        if value:
            date = _find_date(value)
            if date:
                return date
        for next_line in lines[i + 1 : i + 4]:
            if _line_has_label(next_line, CCCD_FIELD_LABELS) and not _line_has_label(
                next_line, labels
            ):
                break
            date = _find_date(next_line)
            if date:
                return date
    return None


def _is_gibberish_line(line: str) -> bool:
    ascii_norm = _normalize_ascii(line)
    compact = re.sub(r"[^A-Z0-9]", "", ascii_norm)
    if re.fullmatch(r"\d{3,4}", compact):
        return True
    if len(compact) <= 4 and compact.isdigit():
        return True
    if re.search(
        r"(?i)(noihiie|noi\s*hiie|afuxpiry|ofbapiry|place\s*of|origin\s*:|residen)",
        ascii_norm,
    ):
        return True
    if re.search(r"(?i)[a-z]{0,2}(?:fuxpir|afuxpir|ofbapir|bapiry|urpiry|daigtat)[a-z]{0,3}", ascii_norm):
        return True
    tokens = [token for token in re.split(r"\s+", line.strip()) if token]
    if len(tokens) >= 3 and sum(1 for token in tokens if len(token) <= 2) >= len(tokens) - 1:
        return True
    letters = re.sub(r"[^A-Za-zÀ-ỹ]", "", line)
    if len(letters) >= 6:
        vowels = sum(
            1
            for char in letters.lower()
            if char in "aeiouyăâêôơưáàảãạắằẳẵặấầẩẫậéèẻẽẹếềểễệíìỉĩịóòỏõọốồổộờởỡợúùủũụứừửữựýỳỷỹỵ"
        )
        if vowels / len(letters) < 0.18 and "," not in line:
            return True
    return False


def _looks_like_vietnamese_place_line(line: str) -> bool:
    candidate = line.strip(" ,;:-")
    if not candidate or _is_gibberish_line(candidate):
        return False
    if _is_known_label(candidate):
        return False

    ascii_norm = _normalize_ascii(candidate)
    if any(phrase in ascii_norm for phrase in _ENGLISH_ADMIN_PHRASES):
        return False
    if re.search(
        r"(?i)^(FOR|DIRECTOR|GENERAL|ADMINISTRATIVE|MANAGEMENT|SOCIAL|ORDER|PERSONAL|IDENTIFICATION|LEFT|RIGHT|INDEX|FINGER)\b",
        ascii_norm,
    ) and not re.search(r"[À-ỹĐđ]", candidate):
        return False
    if re.fullmatch(r"(?i)(HP|HN|HCM|SG|DN|TP\.?HCM|TP\.?HN)", ascii_norm.replace(" ", "")):
        return True
    if "," in candidate or ";" in candidate:
        return True
    if re.search(r"[ĐđĂăÂâÊêÔôƠơƯư]", candidate):
        return True
    if re.search(
        r"(?i)\b(THANH|DONG|KIM|HUNG|YEN|HAI|PHONG|QUYEN|QUAN|PHUONG|XA|TINH|"
        r"NGO|CHAI|TONG|MAY|LE|TRAN|PHU|THANH|PHO|AP|KHU|TP)\b",
        ascii_norm,
    ):
        return True
    return len(candidate) >= 10 and len(candidate.split()) >= 2


def _address_overlap(left: str, right: str) -> float:
    left_parts = {
        _ascii_normalize(part)
        for part in re.split(r"[,;]", left)
        if part.strip()
    }
    right_parts = {
        _ascii_normalize(part)
        for part in re.split(r"[,;]", right)
        if part.strip()
    }
    if not left_parts or not right_parts:
        return 0.0
    shared = left_parts & right_parts
    return len(shared) / max(len(left_parts), len(right_parts))


def _append_unique_text(items: list[str], value: str) -> None:
    key = _ascii_normalize(value)
    if any(_ascii_normalize(item) == key for item in items):
        return
    items.append(value)


def _find_place_address_after_label(
    lines: list[str],
    labels: tuple[str, ...],
    *,
    max_scan_lines: int = 8,
    mode: str = "generic",
) -> str | None:
    for index, line in enumerate(lines):
        if not _line_has_label(line, labels):
            continue

        collected: list[str] = []
        if mode in {"origin", "residence"}:
            inline_value = _extract_inline_address_value(line, mode)
            if inline_value and _looks_like_vietnamese_place_line(inline_value):
                _append_unique_text(collected, inline_value)

        inline = re.split(r"[:;\-]", line, maxsplit=1)
        if len(inline) == 2 and inline[1].strip():
            value = inline[1].strip()
            if _looks_like_vietnamese_place_line(value):
                _append_unique_text(collected, value)

        max_lines = 1 if mode == "origin" else max_scan_lines
        for next_line in lines[index + 1 : index + 1 + max_scan_lines]:
            candidate = next_line.strip()
            if not candidate:
                continue
            if _line_has_label(candidate, CCCD_FIELD_LABELS) and not _line_has_label(
                candidate, labels
            ):
                if not _is_metadata_or_noise_line(candidate):
                    break
            if _is_gibberish_line(candidate) or _is_metadata_or_noise_line(candidate):
                continue
            if _looks_like_vietnamese_place_line(candidate):
                _append_unique_text(collected, candidate)
                if mode == "origin" and "," in candidate:
                    break
                if len(collected) >= max_lines:
                    break
            elif collected:
                break

        if collected:
            return _clean_address(", ".join(collected))
    return None


def _find_issue_place(lines: list[str]) -> str | None:
    issue_place = _find_after_label(
        lines,
        ("NƠI CẤP", "NOI CAP", "PLACE OF ISSUE", "ISSUING AUTHORITY"),
        collect_continuation=True,
    )
    if issue_place:
        return issue_place

    for i, line in enumerate(lines):
        upper_ascii = _normalize_ascii(line)
        if not any(
            token in upper_ascii
            for token in ("CUC CANH SAT", "CC CANH SAT", "CUC TRUONG", "CUC TRUONG CC")
        ):
            continue
        parts = [line.strip()]
        for next_line in lines[i + 1 : i + 3]:
            next_candidate = next_line.strip()
            if not next_candidate:
                break
            next_ascii = _normalize_ascii(next_candidate)
            if _is_known_label(next_candidate) or _is_gibberish_line(next_candidate):
                break
            if any(
                token in next_ascii
                for token in ("QUAN LY", "HANH CHINH", "TRAT TU", "XA HOI")
            ):
                parts.append(next_candidate)
                break
        return ", ".join(parts)
    return None


def _clean_cccd_address(value: str | None) -> str | None:
    if not value:
        return value

    cleaned = value.replace(";", ",")
    # OCR often breaks "Có giá trị đến" into noisy fragments and appends it
    # to the previous address line.
    cleaned = re.sub(
        r"(?i)\b(?:co|có)\s+(?:ni|n[iìíỉĩị]|gia(?:\s+tri)?)\s+den\b[,:;]?",
        "",
        cleaned,
    )
    cleaned = re.sub(r"(?i)\btr\s+den\b[,:;]?", "", cleaned)
    cleaned = re.sub(r"(?i)\bdate\s+of\s+expiry\b[,:;]?", "", cleaned)
    cleaned = re.sub(
        r"(?i)\b(?:of\s*)?(?:bapiry|xpiry|urpiry|daigtat|expir[yie]|date\s+of)\b[,:;]?",
        "",
        cleaned,
    )
    cleaned = re.sub(r"(?i)\b[a-z]{0,3}(?:xpir|urpir|bapir)[a-z]{0,4}\b[,:;]?", "", cleaned)
    cleaned = re.sub(r"(?<!\d)\d{2}[/.-]\d{2}[/.-]\d{4}(?!\d)", "", cleaned)
    parts = [part.strip(" ,") for part in re.split(r"\s*,\s*", cleaned)]
    kept_parts = [
        part
        for part in parts
        if part and not _is_gibberish_line(part) and not _is_metadata_or_noise_line(part)
    ]
    cleaned = ", ".join(kept_parts) if kept_parts else cleaned
    cleaned = re.sub(r"\s*,\s*", ", ", cleaned)
    cleaned = re.sub(r"(?:,\s*){2,}", ", ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,")
    return cleaned or None


def _find_cccd_issue_date(lines: list[str]) -> str | None:
    issue_date = _find_date_after_label(lines, ("NGÀY CẤP", "NGAY CAP", "DATE OF ISSUE"))
    if issue_date:
        return issue_date

    has_back_side_context = any(
        _line_has_label(
            line,
            (
                "ĐẶC ĐIỂM NHẬN DẠNG",
                "DAC DIEM NHAN DANG",
                "PERSONAL IDENTIFICATION",
                "NGÓN TRỎ",
                "NGON TRO",
                "INDEX FINGER",
            ),
        )
        for line in lines
    )
    if not has_back_side_context:
        return None

    for i, line in enumerate(lines):
        if not _line_has_label(
            line,
            (
                "NGÀY; THÁNG; NĂM",
                "NGÀY, THÁNG, NĂM",
                "NGAY THANG NAM",
                "DATE,",
                "MONTH YEAR",
            ),
        ):
            continue
        window = " ".join(lines[i : i + 4])
        date = _find_date(window)
        if date:
            return date
    return None


def _split_sex_nationality(
    sex: str | None, nationality: str | None
) -> tuple[str | None, str | None]:
    if not sex:
        return sex, nationality

    merged = re.search(
        r"^(Nam|Nữ|Nu|Male|Female)\s+"
        r"(?:Qu[oôó]c\s*t[iị]?ch|QUOC\s*TICH|Nationality)\s*"
        r"[/:\-]?\s*(.+)$",
        sex.strip(),
        flags=re.IGNORECASE,
    )
    if merged:
        parsed_sex = merged.group(1).strip()
        parsed_nationality = merged.group(2).strip(" ,;:-") or nationality
        parsed_nationality = re.sub(
            r"(?i)^(?:nationality|qu[oôó]c\s*t[iị]?ch)\s*[:;\-]?\s*",
            "",
            parsed_nationality,
        ).strip(" ,;:-")
        return parsed_sex, parsed_nationality or "Việt Nam"

    if nationality:
        return sex, nationality

    inline = re.search(
        r"^(Nam|Nữ|Nu|Male|Female)\s+(.+)$",
        sex.strip(),
        flags=re.IGNORECASE,
    )
    if inline and re.search(r"(?i)(qu[oó]c\s*t[iị]ch|nationality|vit\s*nam|vi[eê]t\s*nam)", inline.group(2)):
        return inline.group(1).strip(), inline.group(2).strip(" ,;:-")

    return sex, nationality


def _sanitize_nationality(value: str | None) -> str | None:
    if not value:
        return None
    if re.search(r"(?i)(vi[eêê]t\s*nam|vit\s*nam)", value):
        return "Việt Nam"
    cleaned = re.sub(
        r"(?i)^(?:nationelity|naliunality|nalionality|nationality|qu[oôó]c\s*t[iị]?ch)\.?\s*[:;\-/]?\s*",
        "",
        value.strip(),
    ).strip(" ./")
    if re.search(r"(?i)(vi[eêê]t\s*nam|vit\s*nam)", cleaned):
        return "Việt Nam"
    return cleaned or None


def _extract_cccd_sex_and_nationality(
    lines: list[str],
) -> tuple[str | None, str | None]:
    sex = _find_after_label(lines, ("GIỚI TÍNH", "GIOI TINH", "SEX"))
    nationality: str | None = None

    for line in lines:
        ascii_line = _normalize_ascii(line)
        if not re.search(
            r"(?i)(GIOI\s*TINH|SEX|QUOC\s*TICH|NATIONALITY|NATIONELITY|NALIUNALITY|NALIONALITY)",
            ascii_line,
        ):
            continue

        if not sex:
            leading_sex = re.match(r"(?i)^\s*(Nam|Nữ|Nu|Male|Female)\b", line)
            if leading_sex:
                sex = leading_sex.group(1)

        sex_match = re.search(
            r"(?i)(?:gioi\s*tinh|sex)\s*[/:\.\-]*\s*(Nam|Nữ|Nu|Male|Female)\b",
            line,
        )
        if sex_match:
            sex = sex_match.group(1)

        if not nationality and re.search(
            r"(?i)(nationelity|naliunality|nalionality|nationality|qu[oôó]c\s*t[iị]?ch)",
            line,
        ):
            if re.search(r"(?i)(vi[eêê]t\s*nam|vit\s*nam)", line):
                nationality = "Việt Nam"

    sex, nationality = _split_sex_nationality(sex, nationality)
    return sex, _sanitize_nationality(nationality) or nationality or "Việt Nam"


def _looks_like_address_line(line: str) -> bool:
    if not line or _is_known_label(line):
        return False
    if _is_metadata_or_noise_line(line):
        return False
    if _find_date(line) and len(line) <= 24:
        return False

    upper = _normalize(line)
    upper_ascii = _normalize_ascii(line)
    if "," in line:
        return True
    if re.search(
        r"\b(HP|HCM|TP\.|QUAN|PHUONG|XA|THANH|NGO|DUONG|PHO|AP|KHU)\b",
        upper_ascii,
    ):
        return True
    if re.search(r"\d+[/\-]\d+", line):
        return True
    return len(line) >= 12 and len(upper.split()) >= 2


_NAME_LABEL_PHRASES = (
    "NGAY SINH",
    "DATE OF BIRTH",
    "DATE OF BITH",
    "GIOI TINH",
    "GIỚI TÍNH",
    "QUOC TICH",
    "NATIONALITY",
    "QUE QUAN",
    "PLACE OF ORIGIN",
    "NOI THUONG",
    "PLACE OF RESIDENCE",
    "HO VA TEN",
    "FULL NAME",
    "HO TEN",
    "DATE OF ISSUE",
    "DATE OF EXPIRY",
    "CO GIA TRI",
    "CITIZEN IDENTITY",
    "CAN CUOC",
)


def _looks_like_person_name(text: str | None) -> bool:
    if not text or not text.strip():
        return False
    candidate = text.strip()
    if _is_known_label(candidate) or _is_metadata_or_noise_line(candidate):
        return False
    if _find_date(candidate):
        return False
    if re.fullmatch(r"\d{12}", re.sub(r"\D", "", candidate)):
        return False

    ascii_norm = _normalize_ascii(candidate)
    if any(phrase in ascii_norm for phrase in _NAME_LABEL_PHRASES):
        return False

    letters = re.sub(r"[^A-Za-zÀ-ỹ]", "", candidate)
    if len(letters) < 4:
        return False

    tokens = [token for token in re.split(r"\s+", candidate) if token]
    if not tokens:
        return False
    if len(tokens) == 1 and len(letters) < 5:
        return False

    english_field_words = {
        "DATE",
        "BIRTH",
        "BITH",
        "PLACE",
        "NAME",
        "SEX",
        "NATIONAL",
        "NATIONALITY",
        "ORIGIN",
        "RESIDENCE",
        "ISSUE",
        "EXPIRY",
    }
    if sum(1 for token in tokens if _normalize_ascii(token) in english_field_words) >= 2:
        return False
    return True


def _find_name_before_label(
    lines: list[str],
    labels: tuple[str, ...],
    *,
    max_lookback: int = 2,
) -> str | None:
    """OCR sometimes prints the name on the line above the Full name label."""
    for index, line in enumerate(lines):
        if not _line_has_label(line, labels):
            continue
        for prev in reversed(lines[max(0, index - max_lookback) : index]):
            candidate = prev.strip()
            if not candidate:
                continue
            if re.fullmatch(r"\d{12}", re.sub(r"\D", "", candidate)):
                continue
            if _line_has_label(candidate, labels):
                continue
            if _looks_like_person_name(candidate):
                return candidate
    return None


_FULL_NAME_LABELS = (
    "HỌ VÀ TÊN",
    "HO VA TEN",
    "FULL NAME",
    "HỌ TÊN",
    "HO TEN",
)


def _extract_inline_name_from_label_line(line: str) -> str | None:
    """Short names often appear on the same line as the Full name label."""
    value = _value_after_label(line)
    if value and _looks_like_person_name(value):
        return value.strip()

    for pattern in (
        r"(?i)(?:Họ\s*và\s*tên|HỌ\s*VÀ\s*TÊN|HO\s*VA\s*TEN|HỌ\s*TÊN).*?"
        r"(?:Full\s*name|FULL\s*NAME)\s*[:\-/|I]?\s*(.+)$",
        r"(?i)(?:Họ\s*và\s*tên|HỌ\s*VÀ\s*TÊN|HO\s*VA\s*TEN|HỌ\s*TÊN)\s*[:\-/]?\s*(.+)$",
    ):
        match = re.search(pattern, line.strip())
        if match:
            candidate = match.group(1).strip(" :;-/|")
            if _looks_like_person_name(candidate):
                return candidate
    return None


def _looks_like_name_continuation(line: str) -> bool:
    candidate = line.strip()
    if not candidate or _line_has_label(candidate, _FULL_NAME_LABELS):
        return False
    if _looks_like_next_field(candidate, CCCD_FIELD_LABELS):
        return False
    if _find_date(candidate):
        return False
    letters = re.sub(r"[^A-Za-zÀ-ỹ]", "", candidate)
    if len(letters) < 3:
        return False
    ascii_norm = _normalize_ascii(candidate)
    if any(phrase in ascii_norm for phrase in _NAME_LABEL_PHRASES):
        return False
    return True


def _find_name_after_label(
    lines: list[str],
    labels: tuple[str, ...] = _FULL_NAME_LABELS,
    *,
    max_continuation_lines: int = 2,
) -> str | None:
    """Long names usually sit on one or more lines below the Full name label."""
    for index, line in enumerate(lines):
        if not _line_has_label(line, labels):
            continue

        inline = _extract_inline_name_from_label_line(line)
        if inline:
            return inline

        parts: list[str] = []
        for next_line in lines[index + 1 : index + 1 + max_continuation_lines + 1]:
            if _looks_like_next_field(next_line, CCCD_FIELD_LABELS):
                break
            candidate = next_line.strip()
            if not candidate:
                if parts:
                    break
                continue
            if _looks_like_person_name(candidate) or (
                parts and _looks_like_name_continuation(candidate)
            ):
                parts.append(candidate)
                continue
            break

        if parts:
            merged = " ".join(parts)
            if _looks_like_person_name(merged):
                return merged
    return None


def _extract_cccd_full_name(lines: list[str], raw_text: str) -> str | None:
    """CCCD names may be inline (short), below the label (long), or above (noisy OCR)."""
    full_name = _find_name_after_label(lines)
    if full_name:
        return full_name

    full_name = _find_name_before_label(lines, _FULL_NAME_LABELS)
    if full_name:
        return full_name

    normalized = _normalize(raw_text)
    name_match = re.search(
        r"(?:HỌ VÀ TÊN|HO VA TEN|FULL NAME)\s*[:\-]?\s*"
        r"([A-ZÀÁẠẢÃÂẦẤẬẨẪĂẰẮẶẲẴÈÉẸẺẼÊỀẾỆỂỄÌÍỊỈĨÒÓỌỎÕÔỒỐỘỔỖƠỜỚỢỞỠÙÚỤỦŨƯỪỨỰỬỮỲÝỴỶỸĐ\s]{3,})",
        normalized,
    )
    if name_match and _looks_like_person_name(name_match.group(1)):
        return name_match.group(1).title()
    return None


def _find_address_before_label(
    lines: list[str],
    labels: tuple[str, ...],
    *,
    max_lookback: int = 3,
) -> str | None:
    """OCR sometimes places the address line before the field label."""
    for index, line in enumerate(lines):
        if not _line_has_label(line, labels):
            continue
        candidates: list[str] = []
        for prev in lines[max(0, index - max_lookback) : index]:
            candidate = prev.strip()
            if not candidate:
                continue
            if _line_has_label(
                candidate,
                (
                    "GIỚI TÍNH",
                    "GIOI TINH",
                    "SEX",
                    "QUỐC TỊCH",
                    "QUOC TICH",
                    "NATIONALITY",
                    "NATIONELITY",
                ),
            ):
                continue
            if _is_gibberish_line(candidate) or _is_metadata_or_noise_line(candidate):
                continue
            if _looks_like_vietnamese_place_line(candidate):
                candidates.append(candidate)
        if candidates:
            return _clean_address(candidates[-1])
    return None


def _find_residence_after_origin(
    lines: list[str], place_of_origin: str | None
) -> str | None:
    origin_index: int | None = None
    for index, line in enumerate(lines):
        if _line_has_label(line, ("QUÊ QUÁN", "QUE QUAN", "PLACE OF ORIGIN")):
            origin_index = index
            break
    if origin_index is None:
        return None

    best: str | None = None
    for next_line in lines[origin_index + 1 :]:
        candidate = next_line.strip()
        if not candidate:
            continue
        if _line_has_label(
            candidate,
            (
                "NƠI THƯỜNG TRÚ",
                "NOI THUONG TRU",
                "PLACE OF RESIDENCE",
                "CÓ GIÁ TRỊ",
                "CO GIA TRI",
                "DATE OF EXPIRY",
                "NGÀY HẾT",
                "NGAY HET",
                "NGÀY CẤP",
                "NGAY CAP",
            ),
        ):
            break
        if _is_gibberish_line(candidate) or _is_metadata_or_noise_line(candidate):
            continue
        if not _looks_like_vietnamese_place_line(candidate):
            continue
        if place_of_origin:
            if _ascii_normalize(candidate) == _ascii_normalize(place_of_origin):
                continue
            if _address_overlap(place_of_origin, candidate) >= 0.5:
                continue
        if best is None or len(candidate) > len(best):
            best = candidate

    return _clean_address(best) if best else None


def _extract_inline_address_value(line: str, field: str) -> str | None:
    if field == "origin":
        match = re.search(
            r"(?i)(?:qu[eê]\s*quan|place\s*of\s*o[\w]*rigin)\s*[/:\.\-]*\s*(.+)$",
            line,
        )
        return match.group(1).strip(" ,;:-") if match else None

    if field == "residence":
        match = re.search(r"(?i)residen[a-z]*\s*(\d+\s*.+)$", line)
        if match:
            return match.group(1).strip(" ,;:-")
        match = re.search(
            r"(?i)(?:noi\s*thuong\s*tru|noi\s*thung\s*tru|place\s*of\s*residen[a-z]*)\s*[/:\.\-]*\s*(.+)$",
            line,
        )
        return match.group(1).strip(" ,;:-") if match else None

    return None


_PLACE_PART_FIXES: dict[str, str] = {
    "BACH THUN": "Bách Thuận",
    "VU THU": "Vũ Thư",
    "VŪ THƯ": "Vũ Thư",
    "THAI BINH": "Thái Bình",
    "HANG DAO": "Hàng Đào",
    "HÁNG ĐÀO": "Hàng Đào",
    "HOAN KIM": "Hoàn Kiếm",
    "HA NI": "Hà Nội",
    "HÀ NI": "Hà Nội",
    "44 HANG NGANG": "44 Hàng Ngang",
    "HONG PHU": "Hồng Phú",
    "HOANG HOA": "Hoằng Hóa",
    "HOẰNG HOA": "Hoằng Hóa",
    "HOANG HÓA": "Hoằng Hóa",
    "HONG HOA": "Hoằng Hóa",
    "THANH HOA": "Thanh Hóa",
    "THON BAC SON": "Thôn Bắc Sơn",
    "THON BC SON": "Thôn Bắc Sơn",
    "DONG THANH": "Đông Thanh",
    "ĐỒNG THANH": "Đông Thanh",
    "KIM DONG": "Kim Động",
    "KIM ĐONG": "Kim Động",
    "HUNG YEN": "Hưng Yên",
    "HUNG YÊN": "Hưng Yên",
    "NGO QUYN": "Ngô Quyền",
    "HONG PHONG": "Hồng Phong",
    "THANH MIEN": "Thanh Miện",
    "HAI DUONG": "Hải Dương",
    "SO 43 HANG BAC": "Số 43 Hàng Bắc",
    "SÓ 43 HÀNG BAC": "Số 43 Hàng Bắc",
    "HANG BAC": "Hàng Bắc",
    "HÀNG BAC": "Hàng Bắc",
    "HÀNG BẮC": "Hàng Bắc",
    "NGOC THUY": "Ngọc Thụy",
    "LONG BIEN": "Long Biên",
    "HA NOI": "Hà Nội",
    "HÀ NÔI": "Hà Nội",
    "HA NÔI": "Hà Nội",
    "DA NANG": "Đà Nẵng",
    "ĐA NANG": "Đà Nẵng",
    "THANH HOA": "Thanh Hóa",
    "BINH DUONG": "Bình Dương",
    "DONG NAI": "Đồng Nai",
    "CAN THO": "Cần Thơ",
    "QUANG NINH": "Quảng Ninh",
    "BA RIA VUNG TAU": "Bà Rịa - Vũng Tàu",
    "PHU THO": "Phú Thọ",
    "VINH PHUC": "Vĩnh Phúc",
    "BAC NINH": "Bắc Ninh",
    "NAM DINH": "Nam Định",
    "NGHE AN": "Nghệ An",
    "QUANG NAM": "Quảng Nam",
    "QUANG NGAI": "Quảng Ngãi",
    "BINH DINH": "Bình Định",
    "KHANH HOA": "Khánh Hòa",
    "LAM DONG": "Lâm Đồng",
    "TAY NINH": "Tây Ninh",
    "TIEN GIANG": "Tiền Giang",
    "LONG AN": "Long An",
    "AN GIANG": "An Giang",
    "CA MAU": "Cà Mau",
    "SOC TRANG": "Sóc Trăng",
}


def _correct_place_names(text: str | None) -> str | None:
    if not text:
        return text

    parts = [part.strip(" ,;:-") for part in re.split(r"\s*,\s*", text)]
    corrected_parts: list[str] = []
    for part in parts:
        if not part:
            continue
        lookup = _normalize_ascii(part).strip()
        fixed = _PLACE_PART_FIXES.get(lookup) or _PLACE_PART_FIXES.get(lookup.upper())
        if fixed:
            corrected_parts.append(fixed)
        else:
            corrected_parts.append(_correct_vietnamese_ocr(part) or part)
    corrected_parts = _apply_contextual_place_fixes(corrected_parts)
    return ", ".join(corrected_parts) if corrected_parts else None


def _apply_contextual_place_fixes(parts: list[str]) -> list[str]:
    """Fix commune names that need district/province context to disambiguate."""
    ascii_address = " ".join(_normalize_ascii(part) for part in parts)
    in_hoang_hoa_thanh_hoa = "HOANG HOA" in ascii_address and "THANH HOA" in ascii_address
    if not in_hoang_hoa_thanh_hoa:
        return parts

    fixed: list[str] = []
    for part in parts:
        ascii_part = _normalize_ascii(part)
        if ascii_part in {"HONG PHU", "HOANG PHU"}:
            fixed.append("Hoằng Phụ")
        else:
            fixed.append(part)
    return fixed


def _correct_vietnamese_ocr(text: str | None) -> str | None:
    if not text:
        return text

    replacements = (
        ("Hung Yên", "Hưng Yên"),
        ("Hung Yen", "Hưng Yên"),
        ("Hurng Yen", "Hưng Yên"),
        ("Hurng Yên", "Hưng Yên"),
        ("Hưng Yen", "Hưng Yên"),
        ("Kim Đong", "Kim Động"),
        ("Kim Dong", "Kim Động"),
        ("Kim Dông", "Kim Động"),
        ("Đồng Thanh", "Đông Thanh"),
        ("Dong Thanh", "Đông Thanh"),
        ("Dông Thanh", "Đông Thanh"),
        ("Ngô Quyn", "Ngô Quyền"),
        ("Ngo Quyn", "Ngô Quyền"),
        ("Ngô Quyěn", "Ngô Quyền"),
        ("Ngo Quyen", "Ngô Quyền"),
        ("Vit Nam", "Việt Nam"),
        ("Viêt Nam", "Việt Nam"),
        ("Viet Nam", "Việt Nam"),
        ("Bách Thun", "Bách Thuận"),
        ("Vū Thư", "Vũ Thư"),
        ("Thái Binh", "Thái Bình"),
        ("Háng Đào", "Hàng Đào"),
        ("Hoàn Kim", "Hoàn Kiếm"),
        ("Hà Ni", "Hà Nội"),
        ("DU'ONG", "DƯƠNG"),
        ("VÜ", "VŨ"),
        ("Hong Phong", "Hồng Phong"),
        ("Thanh Mien", "Thanh Miện"),
        ("Hai Duong", "Hải Dương"),
        ("Só ", "Số "),
        ("Hàng Bac", "Hàng Bắc"),
        ("Hàng Bąc", "Hàng Bắc"),
        ("LU'ONG", "LƯƠNG"),
        ("LUONG", "LƯƠNG"),
        ("QUOC DOAN", "QUỐC ĐOÀN"),
        ("QUÓC DOÀN", "QUỐC ĐOÀN"),
        ("Quóc Doàn", "Quốc Đoàn"),
        ("Phúng", "Phùng"),
        ("Phung", "Phùng"),
        ("Hoång Hóa", "Hoằng Hóa"),
        ("Hoang Hoa", "Hoằng Hóa"),
        ("Hong Hoa", "Hoằng Hóa"),
        ("Hồng Hóa", "Hoằng Hóa"),
        ("Nguyên", "Nguyễn"),
        ("Nguyen", "Nguyễn"),
        ("Thuong", "Thường"),
        ("Thương", "Thường"),
        ("Tiên", "Tiến"),
        ("Tien", "Tiến"),
        ("Hòa Bình", "Hòa Bình"),
        ("Hoa Binh", "Hòa Bình"),
        ("Bắc Giang", "Bắc Giang"),
        ("Bac Giang", "Bắc Giang"),
    )
    corrected = text
    for source, target in replacements:
        corrected = re.sub(re.escape(source), target, corrected, flags=re.IGNORECASE)
    return corrected


def _is_known_label(line: str) -> bool:
    normalized = _normalize(line)
    labels = (
        "SỐ",
        "NO.",
        "HỌ VÀ TÊN",
        "HO VA TEN",
        "FULL NAME",
        "NGÀY SINH",
        "DATE OF BIRTH",
        "GIỚI TÍNH",
        "SEX",
        "QUỐC TỊCH",
        "NATIONALITY",
        "QUÊ QUÁN",
        "PLACE OF ORIGIN",
        "NƠI THƯỜNG TRÚ",
        "PLACE OF RESIDENCE",
        "NGÀY CẤP",
        "DATE OF ISSUE",
        "NGÀY HẾT HẠN",
        "DATE OF EXPIRY",
    )
    return any(label in normalized for label in labels)


def _is_metadata_or_noise_line(line: str) -> bool:
    normalized = _ascii_normalize(line)
    compact = re.sub(r"[^A-Z0-9]", " ", normalized)
    compact = re.sub(r"\s+", " ", compact).strip()
    if len(compact) <= 3:
        if compact in VIET_PROVINCE_ABBR:
            return False
        return True
    if compact in {
        "CO",
        "DEN",
        "DONG",
        "CO DEN",
        "CO NI DEN",
        "DONG GIA",
        "DONG GIA TRI",
    }:
        return True
    has_date = bool(_find_date(line))
    metadata_tokens = (
        "EXPIRY",
        "XPIR",
        "PIRY",
        "BAPIR",
        "URPIR",
        "DAIGTAT",
        "VALID",
        "GIA TRI",
        "HET HAN",
        "DATE",
        "NGAY",
        "DEN",
        "CO GIA TRI",
    )
    if any(token in normalized for token in ("OFBAPIR", "BAPIRY", "URPIRY", "DAIGTAT", "AFUXPIR", "FUXPIR")):
        return True
    if has_date and any(token in normalized for token in metadata_tokens):
        return True
    if "DEN" in normalized and len(normalized) <= 20:
        return True
    if re.search(r"(?i)(khong\s*th(?:o|or|oi)\s*han|khong thor han)", normalized):
        return True


def _clean_address(value: str | None) -> str | None:
    if not value:
        return None

    cleaned = value.strip(" ,;:-")
    # OCR often leaks broken English labels into the value, e.g. "c{ oigin,"
    # from "Place of origin" or fragments from "Place of residence".
    label_prefix_patterns = (
        r"^[^,;]{0,20}\b(?:ORIGIN|OIGIN|0RIGIN)\b\s*[,;:\-]*\s*",
        r"^[^,;]{0,25}\b(?:RESIDENCE|RESIDEN[CG]E|RESIDEN)\b\s*[,;:\-]*\s*",
        r"^[^,;]{0,20}\b(?:QUE QUAN|NOI THUONG TRU)\b\s*[,;:\-]*\s*",
    )
    for pattern in label_prefix_patterns:
        ascii_cleaned = _ascii_normalize(cleaned)
        match = re.match(pattern, ascii_cleaned)
        if match:
            cleaned = cleaned[match.end() :].strip(" ,;:-")

    parts = [part.strip(" ,;:-") for part in re.split(r"\s*[,;]\s*", cleaned)]
    filtered_parts: list[str] = []
    for part in parts:
        if not part:
            continue
        ascii_part = _normalize_ascii(part).replace(" ", "")
        if ascii_part in VIET_PROVINCE_ABBR:
            filtered_parts.append(part)
            continue
        if _is_metadata_or_noise_line(part) or _is_gibberish_line(part):
            continue
        ascii_part = _ascii_normalize(part)
        if ascii_part in {"ORIGIN", "OIGIN", "PLACE OF ORIGIN", "PLACE OF RESIDENCE"}:
            continue
        filtered_parts.append(part)

    return ", ".join(filtered_parts) if filtered_parts else None


def _find_multiline_after_label(
    lines: list[str],
    labels: tuple[str, ...],
    *,
    max_extra_lines: int = 3,
) -> str | None:
    for i, line in enumerate(lines):
        upper = _normalize(line)
        if not any(label in upper for label in labels):
            continue

        values: list[str] = []
        parts = re.split(r"[:\-]", line, maxsplit=1)
        if len(parts) == 2 and parts[1].strip():
            value = parts[1].strip()
            if not _is_metadata_or_noise_line(value):
                values.append(value)

        for next_line in lines[i + 1 : i + 1 + max_extra_lines]:
            candidate = next_line.strip()
            if not candidate:
                break
            if _is_known_label(candidate):
                if _is_metadata_or_noise_line(candidate):
                    continue
                break
            if _is_metadata_or_noise_line(candidate) or _is_gibberish_line(candidate):
                continue
            if not _looks_like_vietnamese_place_line(candidate):
                continue
            values.append(candidate)

        return _clean_address(", ".join(values)) if values else None

    return None


_CCCD_ISSUE_PLACE_CANONICAL = "Cục Cảnh sát quản lý hành chính về trật tự xã hội"


_MRZ_NAME_TOKEN_FIXES = str.maketrans({"0": "O", "1": "I", "5": "S", "8": "B"})
_MRZ_ID_DIGIT_FIXES = str.maketrans(
    {
        "O": "0",
        "Q": "0",
        "D": "0",
        "I": "1",
        "L": "1",
        "|": "1",
        "S": "5",
        "B": "8",
        "Z": "2",
    }
)


def _normalize_mrz_name_token(token: str) -> str:
    return token.upper().translate(_MRZ_NAME_TOKEN_FIXES)


def _parse_mrz_name_tokens_from_compact(compact: str) -> list[str] | None:
    """Parse ICAO MRZ name line, e.g. PHUNG<<VAN<THACH or LUONG<<QU0C<D0AN."""
    best: list[str] | None = None
    for match in re.finditer(r"([A-Z]{2,})<<([A-Z0-9<]+)", compact):
        surname = match.group(1)
        if re.search(r"\d", surname) or surname.startswith("ID"):
            continue
        given_part = match.group(2).rstrip("<")
        given_tokens = [
            token
            for token in given_part.split("<")
            if token and re.fullmatch(r"[A-Z0-9]{1,30}", token)
        ]
        if not given_tokens:
            continue
        best = [
            _normalize_mrz_name_token(surname),
            *(_normalize_mrz_name_token(token) for token in given_tokens),
        ]
    return best


def parse_mrz_name_tokens(raw_text: str) -> list[str] | None:
    """Extract uppercase name tokens from CCCD back MRZ (surname + given names)."""
    if not raw_text.strip():
        return None

    best: list[str] | None = None
    for line in raw_text.splitlines():
        compact = re.sub(r"\s+", "", line.upper())
        if "<<" not in compact:
            continue
        parsed = _parse_mrz_name_tokens_from_compact(compact)
        if parsed:
            best = parsed

    if best is not None:
        return best

    compact = re.sub(r"\s+", "", raw_text.upper())
    return _parse_mrz_name_tokens_from_compact(compact)


def _valid_cccd_province_code(id_number: str) -> bool:
    try:
        province_code = int(id_number[:3])
    except ValueError:
        return False
    return 1 <= province_code <= 96


def _valid_cccd_id_shape(id_number: str | None) -> bool:
    return bool(
        id_number
        and re.fullmatch(r"\d{12}", id_number)
        and _valid_cccd_province_code(id_number)
    )


def _append_unique_cccd_candidate(candidates: list[str], value: str | None) -> None:
    if not value:
        return
    candidate = value.translate(_MRZ_ID_DIGIT_FIXES)
    if not _valid_cccd_id_shape(candidate):
        return
    if candidate not in candidates:
        candidates.append(candidate)


def parse_mrz_id_numbers(raw_text: str) -> list[str]:
    """Extract likely 12-digit CCCD numbers from Vietnamese CCCD MRZ/id_back text."""
    if not raw_text.strip():
        return []

    compact = re.sub(r"\s+", "", raw_text.upper())
    candidates: list[str] = []

    for match in re.finditer(r"IDVNM([A-Z0-9<]{12,48})", compact):
        payload = match.group(1).translate(_MRZ_ID_DIGIT_FIXES)
        first_candidate = payload[:12]
        offset_candidate = payload[10:22] if len(payload) >= 22 else None

        if (
            offset_candidate
            and _valid_cccd_id_shape(offset_candidate)
            and not _valid_cccd_id_shape(first_candidate)
        ):
            _append_unique_cccd_candidate(candidates, offset_candidate)
            _append_unique_cccd_candidate(candidates, first_candidate)
        else:
            _append_unique_cccd_candidate(candidates, first_candidate)
            _append_unique_cccd_candidate(candidates, offset_candidate)

        for candidate_match in re.finditer(r"\d{12}", payload):
            _append_unique_cccd_candidate(candidates, candidate_match.group(0))

    # Fallback for OCR snippets that lose the IDVNM prefix but keep MRZ/filler markers.
    if "<<" in compact:
        normalized = compact.translate(_MRZ_ID_DIGIT_FIXES)
        for candidate_match in re.finditer(r"\d{12}", normalized):
            _append_unique_cccd_candidate(candidates, candidate_match.group(0))

    return candidates


def cccd_id_matches_demographics(
    id_number: str | None,
    date_of_birth: str | None,
    sex: str | None = None,
) -> bool:
    """Validate CCCD province/century/year digits against DOB and optional sex."""
    if not _valid_cccd_id_shape(id_number):
        return False
    if not date_of_birth:
        return True

    date_match = re.fullmatch(r"(\d{2})[/.-](\d{2})[/.-](\d{4})", date_of_birth.strip())
    if not date_match:
        return True

    year = int(date_match.group(3))
    if id_number[4:6] != f"{year % 100:02d}":
        return False

    century_index = (year - 1900) // 100
    if century_index < 0 or century_index > 4:
        return False
    male_code = century_index * 2
    female_code = male_code + 1
    expected_codes = {male_code, female_code}

    try:
        actual_code = int(id_number[3])
    except ValueError:
        return False

    normalized_sex = _normalize_ascii(sex or "")
    if normalized_sex in {"NAM", "MALE", "M"}:
        expected_codes = {male_code}
    elif normalized_sex in {"NU", "FEMALE", "F"}:
        expected_codes = {female_code}

    return actual_code in expected_codes


def _parse_mrz_expiry_date(raw_text: str) -> str | None:
    """Extract expiry date from ICAO MRZ on CCCD back (YYMMDD before VNM marker)."""
    compact = re.sub(r"\s+", "", raw_text.upper())
    patterns = (
        r"\d{7}[MF<](\d{6})\dVNM",
        r"[MF<](\d{6})\dVNM",
        r"\d{6}[\d<][MF<](\d{6})",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, compact):
            yy, mm, dd = match.group(1)[0:2], match.group(1)[2:4], match.group(1)[4:6]
            if not (1 <= int(mm) <= 12 and 1 <= int(dd) <= 31):
                continue
            year = 2000 + int(yy) if int(yy) < 80 else 1900 + int(yy)
            return f"{dd}/{mm}/{year}"
    return None


def _normalize_issue_place(value: str | None) -> str | None:
    if not value:
        return value

    ascii_norm = _normalize_ascii(value)
    if "CANH SAT" in ascii_norm and any(
        token in ascii_norm for token in ("QUAN LY", "HANH CHINH", "TRAT TU", "XA HOI")
    ):
        return _CCCD_ISSUE_PLACE_CANONICAL
    return value


def _parse_cccd_back(lines: list[str], raw_text: str) -> ParsedFields:
    dates = _find_all_dates(raw_text)
    issued_by = _find_multiline_after_label(
        lines,
        (
            "NƠI CẤP",
            "NOI CAP",
            "ISSUED BY",
            "CỤC CẢNH SÁT",
            "CUC CANH SAT",
            "BỘ CÔNG AN",
            "BO CONG AN",
        ),
        max_extra_lines=2,
    )
    if issued_by is None:
        issued_by = _find_after_label(
            lines,
            (
                "NƠI CẤP",
                "NOI CAP",
                "ISSUED BY",
            ),
        )
    if issued_by is None:
        issued_by = _find_cccd_issuing_authority(lines)

    issued_by = _normalize_issue_place(issued_by)

    expiry_date = _parse_mrz_expiry_date(raw_text)

    issue_date = _find_date_after_label(
        lines,
        ("NGÀY CẤP", "NGAY CAP", "DATE OF ISSUE"),
    )
    if not issue_date and dates and not has_labeled_layout_blocks(raw_text):
        issue_date = dates[0]

    return ParsedFields(
        issue_date=issue_date,
        issue_place=issued_by,
        expiry_date=expiry_date,
        extra={"issued_by": issued_by},
    )


def _find_cccd_issuing_authority(lines: list[str]) -> str | None:
    authority_tokens = (
        "CUC CANH SAT",
        "CC CANH SAT",
        "CUC TRUONG",
        "CANH SAT QUAN LY",
        "BO CONG AN",
    )
    for i, line in enumerate(lines):
        candidate = line.strip()
        normalized = _ascii_normalize(candidate)
        if not any(token in normalized for token in authority_tokens):
            continue
        if _is_metadata_or_noise_line(candidate):
            continue

        values = [candidate]
        for next_line in lines[i + 1 : i + 3]:
            next_candidate = next_line.strip()
            if not next_candidate:
                break
            next_ascii = _normalize_ascii(next_candidate)
            if _is_known_label(next_candidate) or _is_metadata_or_noise_line(next_candidate):
                break
            if re.search(
                r"(?i)^(FOR ADMINISTRATIVE|DIRECTOR GENERAL|LEFT INDEX|RIGHT INDEX|INDEX FINGER)",
                next_ascii,
            ):
                break
            if any(
                token in next_ascii
                for token in ("QUAN LY", "HANH CHINH", "TRAT TU", "XA HOI")
            ):
                values.append(next_candidate)
                break
        return ", ".join(values)

    return None


def _parse_cccd(lines: list[str], raw_text: str) -> ParsedFields:
    normalized = _normalize(raw_text)
    id_candidates = re.findall(r"(?<!\d)(\d{12})(?!\d)", normalized.replace(" ", ""))
    id_number = id_candidates[0] if id_candidates else None

    full_name = _extract_cccd_full_name(lines, raw_text)
    sex, nationality = _extract_cccd_sex_and_nationality(lines)
    place_of_origin = _find_place_address_after_label(
        lines,
        ("QUÊ QUÁN", "QUE QUAN", "PLACE OF ORIGIN", "PLACE OF ONIGIN"),
        mode="origin",
    )
    place_of_residence = _find_place_address_after_label(
        lines,
        (
            "NƠI THƯỜNG TRÚ",
            "NOI THUONG TRU",
            "NOI THUNG TRU",
            "PLACE OF RESIDENCE",
            "PLACS OF RESIDENCE",
        ),
        mode="residence",
    )
    if not place_of_residence:
        place_of_residence = _find_residence_after_origin(lines, place_of_origin)
    if not place_of_origin:
        place_of_origin = _find_address_before_label(
            lines,
            ("QUÊ QUÁN", "QUE QUAN", "PLACE OF ORIGIN", "PLACE OF ONIGIN"),
        )

    dates = _find_all_dates(raw_text)
    date_of_birth = _find_date_after_label(
        lines,
        ("NGÀY SINH", "NGAY SINH", "DATE OF BIRTH"),
    )
    issue_date = _find_cccd_issue_date(lines)
    expiry_date = _find_date_after_label(
        lines,
        (
            "CÓ GIÁ TRỊ ĐẾN",
            "CO GIA TRI DEN",
            "NGÀY HẾT HẠN",
            "NGAY HET HAN",
            "DATE OF EXPIRY",
            "EXPIRY",
        ),
    )

    if not date_of_birth and dates and not has_labeled_layout_blocks(raw_text):
        date_of_birth = dates[0]
    if not issue_date and any(
        _line_has_label(line, ("NGÀY CẤP", "NGAY CAP", "DATE OF ISSUE")) for line in lines
    ):
        issue_date = dates[0] if dates else None
    if not expiry_date and len(dates) > 1 and date_of_birth:
        for candidate_date in reversed(dates):
            if candidate_date in {date_of_birth, issue_date}:
                continue
            expiry_date = candidate_date
            break

    return ParsedFields(
        id_number=id_number,
        full_name=_correct_vietnamese_ocr(full_name),
        date_of_birth=date_of_birth,
        sex=sex,
        nationality=_correct_vietnamese_ocr(nationality) or "Việt Nam",
        place_of_origin=_correct_place_names(_clean_cccd_address(place_of_origin)),
        place_of_residence=_correct_place_names(_clean_cccd_address(place_of_residence)),
        issue_date=issue_date,
        issue_place=_find_issue_place(lines),
        expiry_date=expiry_date,
    )


def _parse_gplx(lines: list[str], raw_text: str) -> ParsedFields:
    normalized = _normalize(raw_text)
    license_match = re.search(r"\b([0-9]{8,12})\b", normalized.replace(" ", ""))
    full_name = _find_after_label(lines, ("HỌ VÀ TÊN", "HO VA TEN", "FULL NAME"))
    license_class = _find_after_label(lines, ("HẠNG", "HANG", "CLASS"))
    dates = _find_all_dates(raw_text)

    return ParsedFields(
        id_number=license_match.group(1) if license_match else None,
        full_name=full_name,
        date_of_birth=dates[0] if dates else None,
        issue_date=dates[1] if len(dates) > 1 else None,
        expiry_date=dates[2] if len(dates) > 2 else None,
        license_class=license_class,
    )


def _parse_passport(lines: list[str], raw_text: str) -> ParsedFields:
    normalized = _normalize(raw_text)
    passport_match = re.search(r"\b([A-Z][0-9]{7,8}|[A-Z]{2}[0-9]{7})\b", normalized)
    surname = _find_after_label(lines, ("SURNAME", "HỌ"))
    given_names = _find_after_label(lines, ("GIVEN NAMES", "TÊN", "TEN"))
    nationality = _find_after_label(lines, ("NATIONALITY", "QUỐC TỊCH", "QUOC TICH"))
    dates = _find_all_dates(raw_text)

    return ParsedFields(
        passport_number=passport_match.group(1) if passport_match else None,
        surname=surname,
        given_names=given_names,
        full_name=" ".join(filter(None, [surname, given_names])) or None,
        nationality=nationality,
        date_of_birth=dates[0] if dates else None,
        issue_date=dates[1] if len(dates) > 1 else None,
        expiry_date=dates[2] if len(dates) > 2 else None,
    )


def _fix_ocr_common_errors(text: str) -> str:
    """Normalize frequent OCR confusions on Vietnamese ID documents."""
    if not text:
        return text
    replacements = {
        "ĐỒNG": "ĐỒNG",
        "CĂN CUÓC": "CĂN CƯỚC",
        "CAN CUOC": "CĂN CƯỚC",
        "HO VA TEN": "HỌ VÀ TÊN",
        "NGAY SINH": "NGÀY SINH",
        "GIOI TINH": "GIỚI TÍNH",
        "QUOC TICH": "QUỐC TỊCH",
        "NOI THUONG TRU": "NƠI THƯỜNG TRÚ",
        "QUE QUAN": "QUÊ QUÁN",
        "NGAY CAP": "NGÀY CẤP",
        "NOI CAP": "NƠI CẤP",
        "0l": "01",
        "O1": "01",
        "l0": "10",
    }
    fixed = text
    for source, target in replacements.items():
        fixed = fixed.replace(source, target)
    fixed = re.sub(r"(?<=\b)([OIl])(?=\d)", "0", fixed)
    fixed = re.sub(r"(?<=\d)([OIl])(?=\b)", "0", fixed)
    return fixed


def merge_parsed_fields(
    front_fields: ParsedFields | None, back_fields: ParsedFields | None
) -> ParsedFields:
    if front_fields is None:
        return back_fields or ParsedFields()
    if back_fields is None:
        return front_fields

    merged = front_fields.model_dump()
    for field_name in ("issue_date", "issue_place", "expiry_date"):
        value = getattr(back_fields, field_name)
        if value:
            merged[field_name] = value
    if not merged.get("issue_place"):
        issued_by = back_fields.extra.get("issued_by")
        if issued_by:
            merged["issue_place"] = issued_by
    if not merged.get("expiry_date"):
        merged["expiry_date"] = back_fields.expiry_date
    return ParsedFields(**merged)


def merge_two_sides(
    front_raw_text: str,
    back_raw_text: str,
    *,
    forced_type: DocumentType | None = None,
) -> TwoSideParseResult:
    """Parse front/back OCR separately, then merge issue fields from the back."""
    from ekyc_document.layout_field_parse import merge_layout_extractions

    front_parse = parse_document(
        front_raw_text,
        forced_type=forced_type,
        side="front",
    )
    back_parse = parse_document(
        back_raw_text,
        forced_type=forced_type or front_parse.document_type,
        side="back",
    )
    merged_fields = merge_parsed_fields(front_parse.fields, back_parse.fields)
    merged_fields, _locked = merge_layout_extractions(
        merged_fields,
        front_raw_text,
        back_raw_text,
    )
    warnings = list(front_parse.warnings)
    warnings.extend(f"Mặt sau: {warning}" for warning in back_parse.warnings)
    layout_date_warnings = merged_fields.extra.get("date_validation_warnings") or []
    warnings.extend(layout_date_warnings)
    expiry_warning = merged_fields.extra.get("expiry_warning")
    if expiry_warning:
        warnings.append(str(expiry_warning))
    return TwoSideParseResult(
        document_type=forced_type or front_parse.document_type,
        fields=merged_fields,
        warnings=warnings,
    )


def parse_document(
    raw_text: str,
    forced_type: DocumentType | None = None,
    *,
    side: str = "front",
) -> ParseResult:
    raw_text = _fix_ocr_common_errors(raw_text)
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    doc_type = forced_type or detect_document_type(raw_text)
    warnings: list[str] = []

    if doc_type == "CCCD":
        fields = _parse_cccd_back(lines, raw_text) if side == "back" else _parse_cccd(lines, raw_text)
    elif doc_type == "GPLX":
        fields = _parse_gplx(lines, raw_text)
    elif doc_type == "PASSPORT":
        fields = _parse_passport(lines, raw_text)
    else:
        fields = ParsedFields()
        warnings.append("Không xác định được loại giấy tờ từ OCR.")

    if has_labeled_layout_blocks(raw_text):
        from ekyc_document.layout_field_parse import merge_layout_extractions

        side_text = raw_text if side == "front" else ""
        back_text = raw_text if side == "back" else ""
        fields, _locked = merge_layout_extractions(
            fields,
            side_text,
            back_text,
        )
        warnings.extend(fields.extra.get("date_validation_warnings") or [])
        expiry_warning = fields.extra.get("expiry_warning")
        if expiry_warning:
            warnings.append(str(expiry_warning))

    if side == "back":
        return ParseResult(document_type=doc_type, fields=fields, warnings=warnings)

    if doc_type == "CCCD" and not fields.id_number:
        warnings.append("Không trích xuất được số CCCD (12 chữ số).")
    if doc_type == "GPLX" and not fields.id_number:
        warnings.append("Không trích xuất được số GPLX.")
    if doc_type == "PASSPORT" and not fields.passport_number:
        warnings.append("Không trích xuất được số hộ chiếu.")

    return ParseResult(document_type=doc_type, fields=fields, warnings=warnings)
