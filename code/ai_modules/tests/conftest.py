"""Test defaults."""

from __future__ import annotations

import os


def pytest_configure(config) -> None:
    os.environ.setdefault("EKYC_INTERNAL_API_KEY", "test-internal-api-key")
    config.addinivalue_line(
        "markers",
        "slow: integration tests that run real OCR/models",
    )
