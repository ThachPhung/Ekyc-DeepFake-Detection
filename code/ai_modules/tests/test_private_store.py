import os
import stat
import tempfile
from pathlib import Path

import pytest

from ekyc_document.config import PipelineConfig
from ekyc_document.private_store import (
    PrivateRecordNotFound,
    PrivateRecordStore,
    extract_front_private_fields,
)
from ekyc_document.schemas import ParsedFields


def test_extract_front_cccd_fields():
    parsed = ParsedFields(
        id_number="001201123456",
        full_name="NGUYEN VAN A",
        date_of_birth="01/01/2001",
        place_of_origin="Thanh Hoa",
        place_of_residence="Quan 1, TP.HCM",
        issue_date="02/02/2022",
        issue_place="Cuc Canh sat QLHC ve TTXH",
        expiry_date="01/01/2031",
    )
    fields = extract_front_private_fields(parsed, "CCCD")
    assert fields["document_number"] == "001201123456"
    assert fields["full_name"] == "NGUYEN VAN A"
    assert fields["place_of_origin"] == "Thanh Hoa"
    assert fields["place_of_residence"] == "Quan 1, TP.HCM"
    assert fields["issue_date"] == "02/02/2022"
    assert fields["issue_place"] == "Cuc Canh sat QLHC ve TTXH"


def test_save_and_load_json_record():
    with tempfile.TemporaryDirectory() as tmp:
        config = PipelineConfig(private_storage_dir=Path(tmp))
        store = PrivateRecordStore(config)
        parsed = ParsedFields(
            id_number="001201123456",
            full_name="NGUYEN VAN A",
            date_of_birth="01/01/2001",
            place_of_origin="Thanh Hoa",
            place_of_residence="Quan 1",
            issue_date="02/02/2022",
            issue_place="Cuc Canh sat QLHC ve TTXH",
            expiry_date="01/01/2031",
        )
        record_id = store.save_front_record(
            document_type="CCCD",
            parsed_fields=parsed,
            ocr_confidence=0.91,
            image_quality_score=0.82,
        )
        loaded = store.load_record(record_id)
        assert loaded["fields"]["full_name"] == "NGUYEN VAN A"
        assert loaded["fields"]["place_of_origin"] == "Thanh Hoa"
        assert loaded["fields"]["issue_date"] == "02/02/2022"
        assert loaded["fields"]["issue_place"] == "Cuc Canh sat QLHC ve TTXH"
        assert loaded["side"] == "front"

        record_path = config.private_storage_dir / "records" / f"{record_id}.json"
        assert record_path.exists()
        assert "NGUYEN VAN A" in record_path.read_text(encoding="utf-8")
        if os.name != "nt":
            mode = record_path.stat().st_mode
            assert mode & stat.S_IRWXG == 0
            assert mode & stat.S_IRWXO == 0


def test_load_missing_record_raises():
    with tempfile.TemporaryDirectory() as tmp:
        store = PrivateRecordStore(PipelineConfig(private_storage_dir=Path(tmp)))
        with pytest.raises(PrivateRecordNotFound):
            store.load_record("00000000-0000-4000-8000-000000000000")


def test_save_result_record_stores_full_payload_privately():
    with tempfile.TemporaryDirectory() as tmp:
        config = PipelineConfig(private_storage_dir=Path(tmp))
        store = PrivateRecordStore(config)

        record_id, path = store.save_result_record(
            record_type="ekyc-video",
            payload={
                "decision": "consider",
                "risk": {"score": 0.62, "reason_codes": ["replay_attack"]},
            },
        )

        loaded = store.load_record(record_id)
        assert path == config.private_storage_dir / "records" / f"{record_id}.json"
        assert loaded["record_type"] == "ekyc-video"
        assert loaded["payload"]["risk"]["reason_codes"] == ["replay_attack"]
