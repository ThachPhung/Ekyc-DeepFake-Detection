"""Speech verification with streaming ASR (ViStreamASR U2 + PhoWhisper refine)."""

from __future__ import annotations

import random
from pathlib import Path
from typing import Callable

from ekyc_document.config import PipelineConfig
from ekyc_document.schemas import DecisionType, VoiceChallengeResult
from ekyc_document.speech.audio import (
    analyze_audio_samples,
    analyze_audio_wav,
    convert_audio_to_wav,
    extract_audio_from_video,
    pcm16_bytes_to_samples,
    shutil_which,
    wav_bytes_to_samples,
)
from ekyc_document.speech.streaming import HybridStreamingTranscriber, StreamingASRSession
from ekyc_document.speech.text_utils import (
    VOICE_CHALLENGE_CODE_DIGITS,
    challenge_templates,
    digits_to_vietnamese_words,
    normalize_vietnamese_text,
    token_overlap_similarity,
    voice_decision_from_wer,
    word_error_rate,
)
from ekyc_document.speech.vad import trim_silence

TranscribeFn = Callable[[Path, PipelineConfig], tuple[str, str]]


class SpeechVerifier:
    """Streaming Vietnamese ASR + challenge text verification."""

    def __init__(
        self,
        config: PipelineConfig | None = None,
        *,
        transcribe_fn: TranscribeFn | None = None,
    ) -> None:
        self.config = config or PipelineConfig()
        self._transcribe_fn = transcribe_fn
        self._streaming: HybridStreamingTranscriber | None = None

    def generate_challenge_phrase(self, seed: int | None = None) -> str:
        return self.generate_voice_challenge(seed=seed)["expected_text"]

    def generate_voice_challenge(self, seed: int | None = None) -> dict[str, str]:
        rng = random.Random(seed)
        base = rng.choice(challenge_templates())
        code = "".join(str(rng.randint(0, 9)) for _ in range(VOICE_CHALLENGE_CODE_DIGITS))
        code_words = " ".join(digits_to_vietnamese_words(digit) for digit in code)
        return {
            "expected_text": f"{base} mã xác nhận {code_words}",
            "numeric_code": code,
            "instruction": "Vui lòng đọc to và rõ câu trên khi quay video.",
        }

    def create_stream_session(self) -> StreamingASRSession:
        return self._streaming_transcriber.create_session()

    def verify_video(
        self,
        video_bytes: bytes,
        expected_text: str,
        *,
        client_transcript: str | None = None,
    ) -> VoiceChallengeResult:
        return self._verify_media(
            video_bytes,
            expected_text,
            media_kind="video",
            client_transcript=client_transcript,
        )

    def verify_audio(
        self,
        audio_bytes: bytes,
        expected_text: str,
        *,
        client_transcript: str | None = None,
    ) -> VoiceChallengeResult:
        return self._verify_media(
            audio_bytes,
            expected_text,
            media_kind="audio",
            client_transcript=client_transcript,
        )

    def verify_transcript(self, expected_text: str, transcript: str, *, method: str) -> VoiceChallengeResult:
        return self._score_transcript(
            expected_text=expected_text,
            transcript=transcript,
            method=method,
            warnings=[],
            audio_detected=True,
        )

    def diagnostics(self) -> dict[str, object]:
        streaming = self._streaming_transcriber.diagnostics()
        return {
            "enabled": self.config.speech_enabled,
            "engine": self.config.speech_engine,
            "streaming": streaming,
            "whisper_model_size": self.config.whisper_model_size,
            "phowhisper_model": self.config.phowhisper_model,
            "ffmpeg_available": shutil_which("ffmpeg") is not None,
            "thresholds": {
                "wer_pass": self.config.voice_wer_pass_threshold,
                "wer_consider": self.config.voice_wer_consider_threshold,
                "min_audio_rms": self.config.min_audio_rms,
                "min_audio_duration_ms": self.config.min_audio_duration_ms,
            },
        }

    @property
    def _streaming_transcriber(self) -> HybridStreamingTranscriber:
        if self._streaming is None:
            self._streaming = HybridStreamingTranscriber(self.config)
        return self._streaming

    def _verify_media(
        self,
        media_bytes: bytes,
        expected_text: str,
        *,
        media_kind: str,
        client_transcript: str | None = None,
    ) -> VoiceChallengeResult:
        warnings: list[str] = []
        if not expected_text.strip():
            return self._empty_expected_result(expected_text)

        if not self.config.speech_enabled:
            return VoiceChallengeResult(
                expected_text=expected_text,
                transcript="",
                normalized_expected=normalize_vietnamese_text(expected_text),
                normalized_transcript="",
                wer=1.0,
                similarity=0.0,
                passed=False,
                decision="failed",
                audio_detected=False,
                method="disabled",
                warnings=["Speech verification đang tắt (EKYC_SPEECH_ENABLED=false)."],
            )

        if client_transcript and client_transcript.strip():
            warnings.append("Đã nhận transcript streaming từ client.")
            return self._score_transcript(
                expected_text=expected_text,
                transcript=client_transcript.strip(),
                method="client_streaming_asr",
                warnings=warnings,
                audio_detected=True,
            )

        if media_kind == "video":
            wav_bytes, extract_warnings = extract_audio_from_video(
                media_bytes,
                sample_rate=self.config.speech_sample_rate,
            )
        else:
            wav_bytes, extract_warnings = convert_audio_to_wav(
                media_bytes,
                sample_rate=self.config.speech_sample_rate,
            )
        warnings.extend(extract_warnings)
        if wav_bytes is None:
            return self._failed_result(
                expected_text=expected_text,
                transcript="",
                method="audio_extract_failed" if media_kind == "video" else "audio_convert_failed",
                warnings=warnings
                or ["Không trích được audio. Kiểm tra ffmpeg và audio track."],
            )

        samples, sample_rate = wav_bytes_to_samples(wav_bytes)
        trimmed, _, vad_ratio = trim_silence(
            samples,
            sample_rate=sample_rate,
            use_webrtc=self.config.speech_vad_enabled,
        )
        analysis_samples = trimmed if trimmed.size > 0 else samples
        duration_ms, rms, energy_ratio = analyze_audio_samples(
            analysis_samples,
            sample_rate=sample_rate,
        )
        speech_ratio = max(vad_ratio, energy_ratio)

        if duration_ms < self.config.min_audio_duration_ms:
            warnings.append("Audio quá ngắn so với yêu cầu đọc challenge.")
        if rms < self.config.min_audio_rms:
            warnings.append("Không phát hiện tiếng nói đủ mạnh.")
        if speech_ratio < self.config.min_speech_ratio:
            warnings.append("Tỷ lệ frame có tiếng nói thấp sau VAD.")

        audio_detected = (
            duration_ms >= self.config.min_audio_duration_ms and rms >= self.config.min_audio_rms
        )
        if not audio_detected:
            return self._failed_result(
                expected_text=expected_text,
                transcript="",
                method="no_speech_detected",
                warnings=warnings,
                audio_duration_ms=duration_ms,
                audio_rms=rms,
                speech_ratio=speech_ratio,
            )

        try:
            if self._transcribe_fn is not None:
                import tempfile

                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
                    path = Path(handle.name)
                    handle.write(wav_bytes)
                try:
                    transcript, method = self._transcribe_fn(path, self.config)
                finally:
                    path.unlink(missing_ok=True)
            else:
                transcript, method = self._streaming_transcriber.transcribe(
                    analysis_samples,
                    sample_rate=sample_rate,
                )
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Streaming STT lỗi: {exc}")
            return self._failed_result(
                expected_text=expected_text,
                transcript="",
                method="stt_error",
                warnings=warnings,
                audio_duration_ms=duration_ms,
                audio_rms=rms,
                speech_ratio=speech_ratio,
            )

        return self._score_transcript(
            expected_text=expected_text,
            transcript=transcript,
            method=method,
            warnings=warnings,
            audio_duration_ms=duration_ms,
            audio_rms=rms,
            speech_ratio=speech_ratio,
        )

    def _score_transcript(
        self,
        *,
        expected_text: str,
        transcript: str,
        method: str,
        warnings: list[str],
        audio_detected: bool = True,
        audio_duration_ms: float | None = None,
        audio_rms: float | None = None,
        speech_ratio: float | None = None,
    ) -> VoiceChallengeResult:
        normalized_expected = normalize_vietnamese_text(expected_text)
        normalized_transcript = normalize_vietnamese_text(transcript)
        wer = word_error_rate(normalized_expected, normalized_transcript)
        similarity = round(
            max(
                0.0,
                1.0 - wer,
                token_overlap_similarity(normalized_expected, normalized_transcript),
            ),
            4,
        )
        decision = voice_decision_from_wer(
            wer,
            pass_threshold=self.config.voice_wer_pass_threshold,
            consider_threshold=self.config.voice_wer_consider_threshold,
        )
        passed = decision == "match"
        if decision == "failed":
            warnings.append("Nội dung giọng nói không khớp câu challenge.")
        elif decision == "consider":
            warnings.append("Nội dung giọng nói gần khớp, cần xem xét thêm.")

        return VoiceChallengeResult(
            expected_text=expected_text,
            transcript=transcript,
            normalized_expected=normalized_expected,
            normalized_transcript=normalized_transcript,
            wer=wer,
            similarity=similarity,
            passed=passed,
            decision=decision,
            audio_detected=audio_detected,
            audio_duration_ms=audio_duration_ms,
            audio_rms=audio_rms,
            speech_ratio=speech_ratio,
            method=method,
            warnings=warnings,
        )

    def _failed_result(
        self,
        *,
        expected_text: str,
        transcript: str,
        method: str,
        warnings: list[str],
        audio_duration_ms: float | None = None,
        audio_rms: float | None = None,
        speech_ratio: float | None = None,
    ) -> VoiceChallengeResult:
        return VoiceChallengeResult(
            expected_text=expected_text,
            transcript=transcript,
            normalized_expected=normalize_vietnamese_text(expected_text),
            normalized_transcript=normalize_vietnamese_text(transcript),
            wer=1.0,
            similarity=0.0,
            passed=False,
            decision="failed",
            audio_detected=False,
            audio_duration_ms=audio_duration_ms,
            audio_rms=audio_rms,
            speech_ratio=speech_ratio,
            method=method,
            warnings=warnings,
        )

    def _empty_expected_result(self, expected_text: str) -> VoiceChallengeResult:
        return VoiceChallengeResult(
            expected_text=expected_text,
            transcript="",
            normalized_expected="",
            normalized_transcript="",
            wer=1.0,
            similarity=0.0,
            passed=False,
            decision="failed",
            audio_detected=False,
            method="not_run",
            warnings=["Thiếu expected_text cho speech verification."],
        )
