"""Check ONNX / OCR runtime readiness for eKYC AI."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from ekyc_document.config import PipelineConfig
from ekyc_document.onnx_models import OnnxModelRegistry
from ekyc_document.speech import SpeechVerifier


def build_readiness_report() -> dict[str, object]:
    config = PipelineConfig()
    onnx = OnnxModelRegistry(config)
    speech = SpeechVerifier(config).diagnostics()
    missing = onnx.ensure_required_models()
    smoke = onnx.smoke_test()

    ocr_ready = True
    ocr_detail = config.ocr_engine
    if config.ocr_engine in {"rapidocr_ppocrv5", "rapidocr_ppocrv6", "rapidocr"}:
        try:
            import rapidocr  # noqa: F401
        except ImportError:
            ocr_ready = False
            ocr_detail = "rapidocr package missing"

    return {
        "ready": not missing and ocr_ready and bool(smoke["ready"]),
        "ocr_engine": config.ocr_engine,
        "ocr_ready": ocr_ready,
        "ocr_detail": ocr_detail,
        "onnx": onnx.diagnostics(),
        "onnx_smoke": smoke,
        "speech": speech,
        "missing_models": missing,
        "models_dir": str(config.models_dir),
    }


def main() -> int:
    report = build_readiness_report()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    sys.exit(main())
