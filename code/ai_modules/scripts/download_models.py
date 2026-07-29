#!/usr/bin/env python3
"""Download ONNX models required for production-grade eKYC AI."""

from __future__ import annotations

import argparse
import hashlib
import sys
import urllib.request
from pathlib import Path

DEFAULT_MODELS = {
    "minifasnet.onnx": {
        "url": "https://github.com/yakhyo/face-anti-spoofing/releases/download/weights/MiniFASNetV2.onnx",
        "sha256": None,
        "description": "MiniFASNetV2 passive liveness (80x80, scale 2.7)",
    },
    "minifasnet_v2se_int8.onnx": {
        "url": None,
        "sha256": None,
        "description": "MiniFASNetV2 INT8 (~600KB) — generate via scripts/quantize_minifasnet.py",
        "generated_from": "minifasnet.onnx",
    },
    "deepfake_detector.onnx": {
        "url": "https://huggingface.co/onnx-community/Deep-Fake-Detector-v2-Model-ONNX/resolve/main/onnx/model_q4.onnx",
        "sha256": None,
        "description": "ViT deepfake detector Q4 (~50MB, 224x224, ImageNet preprocess)",
        "preprocess": "hf_vit",
    },
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {url}")
    print(f"  -> {destination}")
    request = urllib.request.Request(url, headers={"User-Agent": "ekyc-ai-model-downloader/1.0"})
    with urllib.request.urlopen(request, timeout=300) as response, destination.open("wb") as handle:
        total = int(response.headers.get("Content-Length", "0") or 0)
        downloaded = 0
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            handle.write(chunk)
            downloaded += len(chunk)
            if total:
                pct = downloaded * 100 // total
                print(f"  ... {pct}% ({downloaded // (1024 * 1024)} MB)", end="\r")
    print()


def download_models(models_dir: Path, *, force: bool = False) -> int:
    models_dir.mkdir(parents=True, exist_ok=True)
    failures = 0
    manifest_lines = ["# eKYC ONNX model manifest", f"models_dir={models_dir}", ""]

    for filename, spec in DEFAULT_MODELS.items():
        destination = models_dir / filename
        manifest_lines.append(f"[{filename}]")
        manifest_lines.append(f"description={spec['description']}")
        if spec.get("url"):
            manifest_lines.append(f"url={spec['url']}")
        if spec.get("generated_from"):
            manifest_lines.append(f"generated_from={spec['generated_from']}")
        if "preprocess" in spec:
            manifest_lines.append(f"preprocess={spec['preprocess']}")

        if destination.is_file() and not force:
            print(f"Skip existing {destination}")
            manifest_lines.append("status=exists")
            manifest_lines.append("")
            continue

        try:
            spec_url = spec.get("url")
            if not spec_url:
                if destination.is_file():
                    print(f"Skip generated {destination}")
                    manifest_lines.append("status=exists")
                else:
                    print(f"Skip {filename} (generate locally)")
                    manifest_lines.append("status=generate_locally")
                manifest_lines.append("")
                continue

            _download(spec_url, destination)
            digest = _sha256(destination)
            manifest_lines.append(f"sha256={digest}")
            manifest_lines.append("status=downloaded")
            expected = spec.get("sha256")
            if expected and digest != expected:
                print(f"WARNING: sha256 mismatch for {filename}")
                failures += 1
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR downloading {filename}: {exc}")
            manifest_lines.append(f"status=failed ({exc})")
            failures += 1
        manifest_lines.append("")

    manifest_path = models_dir / "MODEL_MANIFEST.txt"
    manifest_path.write_text("\n".join(manifest_lines), encoding="utf-8")
    print(f"Wrote manifest -> {manifest_path}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Download ONNX models for eKYC AI")
    parser.add_argument(
        "--models-dir",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "models",
        help="Directory to store ONNX models (default: code/models)",
    )
    parser.add_argument("--force", action="store_true", help="Re-download even if file exists")
    args = parser.parse_args()
    failures = download_models(args.models_dir, force=args.force)
    if failures:
        print(f"Completed with {failures} failure(s).")
        return 1
    print("All models ready.")
    print("\nRecommended env:")
    print(f"  EKYC_MODELS_DIR={args.models_dir}")
    print(f"  EKYC_MINIFASNET_ONNX_PATH={args.models_dir / 'minifasnet.onnx'}")
    print(f"  EKYC_DEEPFAKE_ONNX_PATH={args.models_dir / 'deepfake_detector.onnx'}")
    print("  EKYC_DEEPFAKE_PREPROCESS=hf_vit")
    print("  EKYC_OCR_ENGINE=rapidocr_ppocrv6")
    print("  EKYC_RAPIDOCR_REC_MODEL=vi")
    print("  EKYC_REQUIRE_ONNX_MODELS=true")
    return 0


if __name__ == "__main__":
    sys.exit(main())
