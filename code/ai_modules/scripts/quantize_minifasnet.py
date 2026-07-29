#!/usr/bin/env python3
"""Quantize MiniFASNet FP32 ONNX to dynamic INT8 (~600KB target)."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


def quantize_minifasnet(
    source: Path,
    destination: Path,
    *,
    copy_to_frontend: Path | None = None,
) -> None:
    if not source.is_file():
        raise FileNotFoundError(f"Không tìm thấy model nguồn: {source}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        from onnxruntime.quantization import QuantType, quantize_dynamic
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "Cần cài onnxruntime: pip install onnxruntime"
        ) from exc

    print(f"Quantizing {source} -> {destination}")
    quantize_dynamic(
        model_input=str(source),
        model_output=str(destination),
        weight_type=QuantType.QUInt8,
    )
    size_kb = destination.stat().st_size / 1024
    print(f"Done. INT8 size: {size_kb:.1f} KB")

    if copy_to_frontend is not None:
        copy_to_frontend.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(destination, copy_to_frontend)
        print(f"Copied to frontend: {copy_to_frontend}")


def main() -> int:
    code_dir = Path(__file__).resolve().parents[2]
    default_source = code_dir / "models" / "minifasnet.onnx"
    default_dest = code_dir / "models" / "minifasnet_v2se_int8.onnx"
    default_frontend = code_dir / "frontend" / "public" / "models" / "minifasnet_v2se_int8.onnx"

    parser = argparse.ArgumentParser(description="Quantize MiniFASNet to INT8 ONNX")
    parser.add_argument("--source", type=Path, default=default_source)
    parser.add_argument("--output", type=Path, default=default_dest)
    parser.add_argument(
        "--copy-frontend",
        type=Path,
        default=default_frontend,
        help="Copy INT8 model for browser WASM inference",
    )
    parser.add_argument("--no-copy-frontend", action="store_true")
    args = parser.parse_args()

    try:
        quantize_minifasnet(
            args.source,
            args.output,
            copy_to_frontend=None if args.no_copy_frontend else args.copy_frontend,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
