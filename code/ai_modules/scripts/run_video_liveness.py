#!/usr/bin/env python3
"""Chạy thử pipeline video liveness từ terminal (không cần frontend)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ekyc_document.biometric import BiometricPipeline
from ekyc_document.config import PipelineConfig
from ekyc_document.speech import SpeechVerifier


def _compact_summary(result: dict) -> dict:
    matching = result.get("matching") or {}
    passive = result.get("passive_liveness") or {}
    voice = result.get("voice_verification") or {}
    risk = result.get("risk") or {}
    return {
        "success": result.get("success"),
        "decision": result.get("decision"),
        "frames_analyzed": result.get("frames_analyzed"),
        "face_frames": result.get("face_frames"),
        "quality_score": result.get("quality_score"),
        "matching_similarity": matching.get("similarity"),
        "matching_decision": matching.get("decision"),
        "passive_liveness_score": passive.get("score"),
        "passive_liveness_method": passive.get("method"),
        "passive_liveness_passed": passive.get("passed"),
        "voice_decision": voice.get("decision"),
        "voice_wer": voice.get("wer"),
        "voice_method": voice.get("method"),
        "risk_score": risk.get("score"),
        "risk_reason_codes": risk.get("reason_codes"),
        "warnings": result.get("warnings"),
        "timings_ms": result.get("timings_ms"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Test video liveness pipeline locally")
    parser.add_argument("--video", type=Path, default=None, help="Video live (.mp4, .webm, ...)")
    parser.add_argument(
        "--doc-face",
        type=Path,
        default=None,
        help="Ảnh chân dung trên CCCD hoặc crop mặt giấy tờ",
    )
    parser.add_argument(
        "--expected-text",
        type=str,
        default=None,
        help="Câu voice challenge (bỏ trống = không check giọng nói)",
    )
    parser.add_argument(
        "--client-transcript",
        type=str,
        default=None,
        help="Transcript từ streaming ASR client (optional)",
    )
    parser.add_argument(
        "--challenge",
        type=str,
        default=None,
        choices=["turn_left", "turn_right", "look_up", "look_down", "blink"],
        help="Active liveness challenge (mặc định: blink)",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="In full JSON thay vì summary",
    )
    parser.add_argument(
        "--gen-challenge",
        action="store_true",
        help="In câu voice challenge mẫu rồi thoát",
    )
    args = parser.parse_args()

    if args.gen_challenge:
        challenge = SpeechVerifier(PipelineConfig()).generate_voice_challenge()
        print(json.dumps(challenge, ensure_ascii=False, indent=2))
        return 0

    if args.video is None or args.doc_face is None:
        parser.error("Cần --video và --doc-face (hoặc dùng --gen-challenge).")
    if not args.video.is_file():
        print(f"ERROR: Không tìm thấy video: {args.video}", file=sys.stderr)
        return 1
    if not args.doc_face.is_file():
        print(f"ERROR: Không tìm thấy ảnh doc_face: {args.doc_face}", file=sys.stderr)
        return 1

    video_bytes = args.video.read_bytes()
    doc_face_bytes = args.doc_face.read_bytes()

    pipeline = BiometricPipeline(PipelineConfig())
    result = pipeline.analyze_video(
        video_bytes,
        doc_face_bytes,
        challenge=args.challenge,
        expected_text=args.expected_text,
        client_transcript=args.client_transcript,
    )
    payload = result.model_dump()
    if args.full:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(_compact_summary(payload), ensure_ascii=False, indent=2))
    return 0 if result.decision == "match" else 1


if __name__ == "__main__":
    raise SystemExit(main())
