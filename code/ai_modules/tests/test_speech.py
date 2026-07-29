from __future__ import annotations

import builtins
import wave
from io import BytesIO

import numpy as np

from ekyc_document.config import PipelineConfig
from ekyc_document.speech import (
    HybridStreamingTranscriber,
    SpeechVerifier,
    analyze_audio_wav,
    normalize_vietnamese_text,
    token_overlap_similarity,
    voice_decision_from_wer,
    word_error_rate,
)


def test_normalize_vietnamese_text_strips_accents_and_punctuation() -> None:
    assert normalize_vietnamese_text("Tôi xác nhận danh tính!") == "toi xac nhan danh tinh"


def test_word_error_rate_exact_and_partial() -> None:
    ref = normalize_vietnamese_text("toi xac nhan danh tinh")
    assert word_error_rate(ref, ref) == 0.0
    assert word_error_rate(ref, "toi xac nhan") == 0.4


def test_token_overlap_similarity() -> None:
    assert token_overlap_similarity("a b c", "a b d") == 0.6667


def test_voice_decision_thresholds() -> None:
    assert voice_decision_from_wer(0.1, pass_threshold=0.25, consider_threshold=0.4) == "match"
    assert voice_decision_from_wer(0.3, pass_threshold=0.25, consider_threshold=0.4) == "consider"
    assert voice_decision_from_wer(0.5, pass_threshold=0.25, consider_threshold=0.4) == "failed"


def test_generate_challenge_phrase_is_deterministic_with_seed() -> None:
    verifier = SpeechVerifier()
    first = verifier.generate_voice_challenge(seed=42)
    second = verifier.generate_voice_challenge(seed=42)
    assert first == second
    assert len(first["numeric_code"]) == 8
    normalized = normalize_vietnamese_text(first["expected_text"])
    _, _, code_words = normalized.partition("ma xac nhan ")
    assert len(code_words.split()) == 8


def test_score_transcript_passes_on_close_match() -> None:
    expected = "Tôi xác nhận danh tính của mình"
    verifier = SpeechVerifier(
        PipelineConfig(),
        transcribe_fn=lambda _path, _config: (
            "toi xac nhan danh tinh cua minh",
            "test/mock",
        ),
    )
    wav_bytes = _synthetic_wav_bytes(duration_sec=1.2, frequency=440.0)
    duration_ms, rms, speech_ratio = analyze_audio_wav(wav_bytes)
    result = verifier._score_transcript(
        expected_text=expected,
        transcript="toi xac nhan danh tinh cua minh",
        method="test/mock",
        warnings=[],
        audio_duration_ms=duration_ms,
        audio_rms=rms,
        speech_ratio=speech_ratio,
    )
    assert result.passed is True
    assert result.decision == "match"
    assert result.wer == 0.0


def test_verify_video_without_expected_text_is_not_run() -> None:
    verifier = SpeechVerifier()
    result = verifier.verify_video(b"video", "")
    assert result.method == "not_run"
    assert result.passed is False


def test_speech_custom_transcribe_fn_is_used() -> None:
    called = {"count": 0}

    def _fake_transcribe(_path, config):
        called["count"] += 1
        assert config.speech_engine == "phowhisper"
        return "toi xac nhan danh tinh", "phowhisper/test"

    verifier = SpeechVerifier(
        PipelineConfig(speech_engine="phowhisper"),
        transcribe_fn=_fake_transcribe,
    )
    wav_bytes = _synthetic_wav_bytes(duration_sec=1.0, frequency=220.0)
    result = verifier.verify_audio(wav_bytes, "Tôi xác nhận danh tính")
    assert called["count"] == 1
    assert result.method == "phowhisper/test"
    assert result.passed is True


def test_hybrid_streaming_transcriber_falls_back_when_phowhisper_refine_fails() -> None:
    transcriber = HybridStreamingTranscriber(
        PipelineConfig(speech_engine="vistream_phowhisper"),
    )
    samples = np.ones(16000, dtype=np.float32) * 0.2

    transcriber._streaming_transcribe = lambda _samples, *, sample_rate: (  # type: ignore[method-assign]
        "nam khong chin bay bon chin",
        "draft/mock",
    )

    def _raise_refine(_samples, *, sample_rate):
        raise NameError("name 'torch' is not defined")

    transcriber._transcribe_phowhisper = _raise_refine  # type: ignore[method-assign]

    transcript, method = transcriber.transcribe(samples, sample_rate=16000)

    assert transcript == "nam khong chin bay bon chin"
    assert method == "draft/mock"


def test_transcribe_phowhisper_reports_missing_transformers(monkeypatch) -> None:
    transcriber = HybridStreamingTranscriber(PipelineConfig(speech_engine="phowhisper"))
    samples = np.ones(1600, dtype=np.float32) * 0.2
    original_import = builtins.__import__

    def _fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "transformers":
            raise ImportError("missing transformers")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _fake_import)

    try:
        transcriber._transcribe_phowhisper(samples, sample_rate=16000)
    except RuntimeError as exc:
        assert "transformers" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError when transformers is unavailable")


def test_analyze_audio_wav_detects_non_silent_signal() -> None:
    wav_bytes = _synthetic_wav_bytes(duration_sec=1.0, frequency=220.0)
    duration_ms, rms, speech_ratio = analyze_audio_wav(wav_bytes)
    assert duration_ms == 1000.0
    assert rms > 0.01
    assert speech_ratio > 0.0


def _synthetic_wav_bytes(*, duration_sec: float, frequency: float) -> bytes:
    sample_rate = 16000
    sample_count = int(sample_rate * duration_sec)
    t = np.linspace(0, duration_sec, sample_count, endpoint=False)
    samples = (0.35 * np.sin(2 * np.pi * frequency * t) * np.iinfo(np.int16).max).astype(np.int16)
    from io import BytesIO

    buffer = BytesIO()
    with wave.open(buffer, "wb") as wav_writer:
        wav_writer.setnchannels(1)
        wav_writer.setsampwidth(2)
        wav_writer.setframerate(sample_rate)
        wav_writer.writeframes(samples.tobytes())
    return buffer.getvalue()
