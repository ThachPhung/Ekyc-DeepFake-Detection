"""Mask sensitive document fields before storing public JSON payloads."""

from __future__ import annotations

from typing import Any


def _mask_identifier(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    visible = min(4, len(text))
    return f"{'*' * max(len(text) - visible, 0)}{text[-visible:]}"


def _mask_name(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    masked_words = []
    for word in text.split():
        if len(word) <= 1:
            masked_words.append("*")
        else:
            masked_words.append(f"{word[0]}{'*' * (len(word) - 1)}")
    return " ".join(masked_words)


def _mask_date(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    visible = min(2, len(text))
    return f"{'*' * max(len(text) - visible, 0)}{text[-visible:]}"


def _mask_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) <= 4:
        return "*" * len(text)
    return f"{text[:2]}{'*' * max(len(text) - 4, 3)}{text[-2:]}"


def _mask_parsed_fields(parsed_fields: dict[str, Any]) -> dict[str, Any]:
    masked = dict(parsed_fields)
    for key in ("id_number", "passport_number"):
        if key in masked:
            masked[key] = _mask_identifier(masked[key])
    if "full_name" in masked:
        masked["full_name"] = _mask_name(masked["full_name"])
    for key in ("date_of_birth", "issue_date", "expiry_date"):
        if key in masked:
            masked[key] = _mask_date(masked[key])
    for key in (
        "address",
        "place_of_origin",
        "place_of_residence",
        "issue_place",
        "surname",
        "given_names",
    ):
        if key in masked:
            masked[key] = _mask_text(masked[key])
    return masked


def mask_document_payload(payload: dict[str, Any]) -> dict[str, Any]:
    masked = dict(payload)
    parsed_fields = masked.get("parsed_fields")
    if isinstance(parsed_fields, dict):
        masked["parsed_fields"] = _mask_parsed_fields(parsed_fields)
    for key in (
        "full_name",
        "id_number",
        "passport_number",
        "date_of_birth",
        "address",
        "place_of_origin",
        "place_of_residence",
        "issue_date",
        "issue_place",
        "expiry_date",
    ):
        if key not in masked:
            continue
        if key in {"id_number", "passport_number"}:
            masked[key] = _mask_identifier(masked[key])
        elif key == "full_name":
            masked[key] = _mask_name(masked[key])
        elif key in {"date_of_birth", "issue_date", "expiry_date"}:
            masked[key] = _mask_date(masked[key])
        else:
            masked[key] = _mask_text(masked[key])
    return masked
