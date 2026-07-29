#!/usr/bin/env python3
"""Shared read/write helpers for .ai-log/session.json (array under ``entries``)."""
from __future__ import annotations

import json
import os
from pathlib import Path

SESSION_NAME = "session.json"
LEGACY_NAME = "session.jsonl"


def log_dir() -> Path:
    return Path(os.environ.get("AI_LOG_DIR", ".ai-log"))


def log_file() -> Path:
    return log_dir() / SESSION_NAME


def legacy_log_file() -> Path:
    return log_dir() / LEGACY_NAME


def _parse_payload(data: object) -> list[dict]:
    if isinstance(data, list):
        return [e for e in data if isinstance(e, dict)]
    if isinstance(data, dict):
        entries = data.get("entries", [])
        if isinstance(entries, list):
            return [e for e in entries if isinstance(e, dict)]
    return []


def _parse_json_text(text: str) -> list[dict]:
    """Load current JSON, concatenated JSON payloads, or a valid prefix with a bad tail."""
    text = text.strip()
    if not text:
        return []

    try:
        return _parse_payload(json.loads(text))
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    idx = 0
    entries: list[dict] = []
    while idx < len(text):
        while idx < len(text) and text[idx].isspace():
            idx += 1
        if idx >= len(text):
            break
        try:
            payload, idx = decoder.raw_decode(text, idx)
        except json.JSONDecodeError:
            break
        entries.extend(_parse_payload(payload))

    if entries:
        return entries

    # Last-resort compatibility with the old JSONL log format.
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.extend(_parse_payload(json.loads(line)))
        except json.JSONDecodeError:
            continue
    return entries


def load_entries(path: Path | None = None) -> list[dict]:
    target = path or log_file()
    if not target.exists() or target.stat().st_size == 0:
        return []
    with open(target, encoding="utf-8-sig") as f:
        return _parse_json_text(f.read())


def save_entries(entries: list[dict], path: Path | None = None) -> None:
    target = path or log_file()
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8") as f:
        json.dump({"entries": entries}, f, ensure_ascii=False, indent=2)
        f.write("\n")


def append_entry(entry: dict) -> None:
    ensure_migrated()
    entries = load_entries()
    entries.append(entry)
    save_entries(entries)


def append_entries(new_entries: list[dict]) -> None:
    if not new_entries:
        return
    ensure_migrated()
    entries = load_entries()
    entries.extend(new_entries)
    save_entries(entries)


def get_logged_entry_ids(path: Path | None = None) -> set[str]:
    ids: set[str] = set()
    for entry in load_entries(path):
        eid = entry.get("entry_id", "")
        if eid:
            ids.add(eid)
    return ids


def migrate_jsonl_to_json(
    jsonl_path: Path | None = None,
    json_path: Path | None = None,
) -> int:
    """Convert legacy session.jsonl → session.json. Returns number of entries migrated."""
    src = jsonl_path or legacy_log_file()
    dst = json_path or log_file()
    if not src.exists() or src.stat().st_size == 0:
        return 0

    migrated: list[dict] = []
    with open(src, encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(entry, dict):
                migrated.append(entry)

    if not migrated:
        return 0

    existing = load_entries(dst) if dst.exists() else []
    seen = {e.get("entry_id") for e in existing if e.get("entry_id")}
    for entry in migrated:
        eid = entry.get("entry_id")
        if eid and eid in seen:
            continue
        existing.append(entry)
        if eid:
            seen.add(eid)

    save_entries(existing, dst)
    return len(migrated)


def ensure_migrated() -> None:
    """One-time migration when only the legacy jsonl file exists."""
    dst = log_file()
    src = legacy_log_file()
    if dst.exists() or not src.exists():
        return
    migrate_jsonl_to_json(src, dst)
