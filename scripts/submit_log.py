#!/usr/bin/env python3
"""
Submit .ai-log/session.json to grading server.
Called by git pre-push hook or manually.

After a successful submit, the live log is rotated:
  - Submitted entries moved into .ai-log/archive/YYYY-MM-DD.json
  - Remaining entries stay in session.json (or file recreated empty)

If the POST fails, the pending file is restored so nothing is lost.
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from log_store import ensure_migrated, load_entries, log_file, save_entries

SERVER_URL = os.environ.get("AI_LOG_SERVER", "")
API_KEY = os.environ.get("AI_LOG_API_KEY", "")
LOG_FILE = log_file()
ARCHIVE_DIR = LOG_FILE.parent / "archive"

# Match server-side MAX_BATCH_ENTRIES so we never get a 422.
BATCH_LIMIT = 500
DEFAULT_BATCH_BYTE_LIMIT = 1_000_000


def _batch_byte_limit() -> int:
    raw = os.environ.get("AI_LOG_BATCH_BYTE_LIMIT", str(DEFAULT_BATCH_BYTE_LIMIT))
    try:
        return max(1024, int(raw))
    except ValueError:
        return DEFAULT_BATCH_BYTE_LIMIT


def _encode_payload(entries: list[dict]) -> bytes:
    return json.dumps({"entries": entries}, ensure_ascii=False).encode("utf-8")


def _pick_batch(all_entries: list[dict]) -> tuple[list[dict], list[dict], bytes]:
    byte_limit = _batch_byte_limit()
    entries: list[dict] = []
    payload = _encode_payload(entries)

    for entry in all_entries[:BATCH_LIMIT]:
        candidate = entries + [entry]
        candidate_payload = _encode_payload(candidate)
        if entries and len(candidate_payload) > byte_limit:
            break
        entries = candidate
        payload = candidate_payload

    return entries, all_entries[len(entries):], payload


def _archive_entries(entries: list[dict]) -> None:
    if not entries:
        return
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    archive_file = ARCHIVE_DIR / f"{today}.json"
    existing = load_entries(archive_file) if archive_file.exists() else []
    existing.extend(entries)
    save_entries(existing, archive_file)


def _restore_pending(pending: Path) -> None:
    pending_entries = load_entries(pending)
    if not pending_entries:
        pending.unlink(missing_ok=True)
        return
    if LOG_FILE.exists():
        merged = pending_entries + load_entries(LOG_FILE)
        save_entries(merged)
        pending.unlink()
    else:
        pending.rename(LOG_FILE)


def main():
    ensure_migrated()

    if not SERVER_URL:
        print("[ai-log] AI_LOG_SERVER not set — skipping submission.", file=sys.stderr)
        sys.exit(0)

    if not LOG_FILE.exists() or LOG_FILE.stat().st_size == 0:
        print("[ai-log] No logs to submit.", file=sys.stderr)
        sys.exit(0)

    pending = LOG_FILE.with_name(f"session.pending.{int(time.time())}.json")
    try:
        LOG_FILE.rename(pending)
    except FileNotFoundError:
        print("[ai-log] No logs to submit.", file=sys.stderr)
        sys.exit(0)

    all_entries = load_entries(pending)
    entries, leftover, payload = _pick_batch(all_entries)

    if not entries:
        pending.unlink(missing_ok=True)
        print("[ai-log] No valid entries to submit.", file=sys.stderr)
        sys.exit(0)

    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"
    req = urllib.request.Request(
        SERVER_URL,
        data=payload,
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"[ai-log] Submitted {len(entries)} entries → {resp.status}", file=sys.stderr)
    except urllib.error.URLError as e:
        _restore_pending(pending)
        print(f"[ai-log] Submit failed: {e} — logs kept locally.", file=sys.stderr)
        sys.exit(0)

    _archive_entries(entries)
    pending.unlink(missing_ok=True)

    if leftover:
        save_entries(leftover)
        print(
            f"[ai-log] {len(leftover)} entries deferred to next push.",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
