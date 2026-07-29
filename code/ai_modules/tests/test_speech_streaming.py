from __future__ import annotations

import numpy as np

from ekyc_document.config import PipelineConfig
from ekyc_document.speech.text_utils import (
    normalize_vietnamese_text,
    voice_decision_from_wer,
    word_error_rate,
)
from ekyc_document.speech.vad import chunk_for_streaming, trim_silence
from ekyc_document.speech.verifier import SpeechVerifier


def test_normalize_vietnamese_text_strips_diacritics() -> None:
    assert normalize_vietnamese_text("Họ và Tên") == "ho va ten"


def test_word_error_rate_identical() -> None:
    text = normalize_vietnamese_text("toi xac nhan danh tinh")
    assert word_error_rate(text, text) == 0.0


def test_voice_decision_from_wer() -> None:
    assert voice_decision_from_wer(0.1, pass_threshold=0.25, consider_threshold=0.4) == "match"
    assert voice_decision_from_wer(0.3, pass_threshold=0.25, consider_threshold=0.4) == "consider"
    assert voice_decision_from_wer(0.9, pass_threshold=0.25, consider_threshold=0.4) == "failed"


def test_trim_silence_keeps_speech_region() -> None:
    sample_rate = 16000
    silence = np.zeros(sample_rate, dtype=np.float32)
    speech = np.full(sample_rate, 0.08, dtype=np.float32)
    samples = np.concatenate([silence, speech, silence])
    trimmed, segments, ratio = trim_silence(samples, sample_rate=sample_rate, use_webrtc=False)
    assert trimmed.size > 0
    assert segments
    assert ratio > 0.2


def test_chunk_for_streaming_640ms() -> None:
    samples = np.ones(16000 * 2, dtype=np.float32)
    chunks = chunk_for_streaming(samples, sample_rate=16000, chunk_ms=640)
    assert len(chunks) >= 3
    assert chunks[0].size == int(16000 * 0.64)


def test_verify_transcript_uses_client_streaming_method() -> None:
    verifier = SpeechVerifier(PipelineConfig())
    expected = "Tôi xác nhận danh tính của mình mã xác nhận một hai ba"
    result = verifier.verify_transcript(expected, expected, method="client_streaming_asr")
    assert result.passed is True
    assert result.method == "client_streaming_asr"


def test_verify_video_accepts_client_transcript_without_ffmpeg(tmp_path) -> None:
    def fake_transcribe(_path, _config):
        return "unused", "should_not_run"

    verifier = SpeechVerifier(
        PipelineConfig(),
        transcribe_fn=fake_transcribe,
    )
    expected = "Tôi xác nhận danh tính của mình"
    result = verifier.verify_video(
        b"fake-video",
        expected,
        client_transcript=expected,
    )
    assert result.passed is True
    assert result.method == "client_streaming_asr"
