"""Private on-disk storage for extracted PII (never exposed in public API responses)."""

from __future__ import annotations

import json
import os
import stat
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ekyc_document.config import PipelineConfig
from ekyc_document.schemas import DocumentType, ParsedFields

RECORD_FILE_SUFFIX = ".json"


class PrivateStoreError(Exception):
    pass


class PrivateRecordNotFound(PrivateStoreError):
    pass


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _restrict_permissions(path: Path) -> None:
    if os.name == "nt" or not path.exists():
        return
    mode = stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR if path.is_dir() else stat.S_IRUSR | stat.S_IWUSR
    os.chmod(path, mode)


def extract_front_private_fields(
    parsed: ParsedFields | None, document_type: DocumentType
) -> dict[str, str | None]:
    """Fields from the front side that must be stored privately."""
    if parsed is None:
        return {
            "full_name": None,
            "document_number": None,
            "date_of_birth": None,
            "place_of_origin": None,
            "place_of_residence": None,
            "issue_date": None,
            "issue_place": None,
            "expiry_date": None,
        }

    if document_type == "PASSPORT":
        return {
            "full_name": parsed.full_name,
            "document_number": parsed.passport_number,
            "date_of_birth": parsed.date_of_birth,
            "place_of_origin": None,
            "place_of_residence": None,
            "issue_date": parsed.issue_date,
            "issue_place": parsed.issue_place,
            "expiry_date": parsed.expiry_date,
        }

    if document_type == "GPLX":
        return {
            "full_name": parsed.full_name,
            "document_number": parsed.id_number,
            "date_of_birth": parsed.date_of_birth,
            "place_of_origin": parsed.place_of_origin,
            "place_of_residence": parsed.place_of_residence,
            "issue_date": parsed.issue_date,
            "issue_place": parsed.issue_place,
            "expiry_date": parsed.expiry_date,
        }

    return {
        "full_name": parsed.full_name,
        "document_number": parsed.id_number,
        "date_of_birth": parsed.date_of_birth,
        "place_of_origin": parsed.place_of_origin,
        "place_of_residence": parsed.place_of_residence,
        "issue_date": parsed.issue_date,
        "issue_place": parsed.issue_place,
        "expiry_date": parsed.expiry_date,
    }


class PrivateRecordStore:
    def __init__(self, config: PipelineConfig | None = None) -> None:
        self.config = config or PipelineConfig()
        self.storage_dir = self.config.private_storage_dir
        self.records_dir = self.storage_dir / "records"
        self.records_dir.mkdir(parents=True, exist_ok=True)
        _restrict_permissions(self.storage_dir)
        _restrict_permissions(self.records_dir)

    def save_front_record(
        self,
        *,
        document_type: DocumentType,
        parsed_fields: ParsedFields | None,
        ocr_confidence: float,
        image_quality_score: float,
        side: str = "front",
    ) -> str:
        record_id = str(uuid.uuid4())
        payload = {
            "record_id": record_id,
            "created_at": _utc_now_iso(),
            "document_type": document_type,
            "side": side,
            "ocr_confidence": round(ocr_confidence, 4),
            "image_quality_score": round(image_quality_score, 4),
            "fields": extract_front_private_fields(parsed_fields, document_type),
        }
        self._write_record(record_id, payload)
        return record_id

    def save_result_record(
        self,
        *,
        record_type: str,
        payload: dict[str, Any],
    ) -> tuple[str, Path]:
        record_id = str(uuid.uuid4())
        saved_payload = {
            "record_id": record_id,
            "created_at": _utc_now_iso(),
            "record_type": record_type,
            "payload": payload,
        }
        path = self._write_record(record_id, saved_payload)
        return record_id, path

    def load_record(self, record_id: str) -> dict[str, Any]:
        if not _is_valid_record_id(record_id):
            raise PrivateStoreError("record_id không hợp lệ.")

        path = self._record_path(record_id)
        if not path.exists():
            raise PrivateRecordNotFound(f"Không tìm thấy bản ghi: {record_id}")

        return json.loads(path.read_text(encoding="utf-8"))

    def _record_path(self, record_id: str) -> Path:
        return self.records_dir / f"{record_id}{RECORD_FILE_SUFFIX}"

    def _write_record(self, record_id: str, payload: dict[str, Any]) -> Path:
        path = self._record_path(record_id)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        _restrict_permissions(path)
        return path


def _is_valid_record_id(record_id: str) -> bool:
    try:
        uuid.UUID(record_id)
        return True
    except ValueError:
        return False
