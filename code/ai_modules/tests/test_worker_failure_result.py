from __future__ import annotations

from worker import ekyc_worker


class DummyRedis:
    def rpush(self, *_args, **_kwargs):  # pragma: no cover - should not be used here
        raise AssertionError("failed final-attempt jobs should not be requeued")


def test_unified_failed_job_persists_failure_payload(monkeypatch) -> None:
    updates = []
    saved = []

    def fake_update_unified_request(**kwargs):
        updates.append(kwargs)

    def fake_save_ekyc_result(**kwargs):
        saved.append(kwargs)
        return "result-id", None

    monkeypatch.setattr(ekyc_worker, "_update_unified_request", fake_update_unified_request)
    monkeypatch.setattr(ekyc_worker, "_save_ekyc_result", fake_save_ekyc_result)
    monkeypatch.setattr(ekyc_worker, "MAX_RETRIES", 1)

    ekyc_worker._handle_failed_job(
        redis_client=DummyRedis(),
        payload={
            "request_id": "request-1",
            "job_type": "EKYC_VERIFY_ALL",
            "attempt": 1,
        },
        exc=ValueError("Khong doc duoc video upload."),
    )

    assert updates[0]["status"] == "FAILED"
    assert updates[0]["decision"] == "failed"
    assert updates[0]["result"]["success"] is False
    assert updates[0]["result"]["video"]["decision"] == "failed"
    assert "Khong doc duoc video upload." in updates[0]["error_message"]

    assert saved[0]["status"] == "FAILED"
    assert saved[0]["result"]["video"]["error_message"] == "Khong doc duoc video upload."
    assert saved[0]["liveness_result"]["decision"] == "failed"
