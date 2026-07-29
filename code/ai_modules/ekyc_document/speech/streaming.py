"""Streaming ASR engines: ViStreamASR (U2) + PhoWhisper refinement."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import numpy as np

from ekyc_document.config import PipelineConfig
from ekyc_document.speech.vad import chunk_for_streaming, trim_silence


class StreamingBackend(Protocol):
    def transcribe_stream(self, samples: np.ndarray, *, sample_rate: int) -> tuple[str, str]:
        ...


@dataclass
class StreamChunkResult:
    partial: bool
    final: bool
    text: str
    method: str


@dataclass
class StreamingASRSession:
    """Incremental streaming session (~640ms/chunk) for WebSocket clients."""

    config: PipelineConfig
    backend: StreamingBackend
    sample_rate: int = 16000
    _buffer: np.ndarray = field(default_factory=lambda: np.array([], dtype=np.float32))
    _latest_text: str = ""
    _method: str = "streaming_asr"

    def ingest_pcm16(self, pcm_bytes: bytes) -> StreamChunkResult | None:
        if not pcm_bytes:
            return None
        pcm16 = np.frombuffer(pcm_bytes, dtype=np.int16)
        chunk = pcm16.astype(np.float32) / 32768.0
        self._buffer = np.concatenate([self._buffer, chunk])
        chunk_size = max(1, int(self.sample_rate * self.config.speech_chunk_size_ms / 1000.0))
        if self._buffer.size < chunk_size:
            return StreamChunkResult(
                partial=True,
                final=False,
                text=self._latest_text,
                method=self._method,
            )

        process_samples = self._buffer.copy()
        self._buffer = np.array([], dtype=np.float32)
        trimmed, _, _ = trim_silence(
            process_samples,
            sample_rate=self.sample_rate,
            use_webrtc=self.config.speech_vad_enabled,
        )
        if trimmed.size == 0:
            return StreamChunkResult(
                partial=True,
                final=False,
                text=self._latest_text,
                method=self._method,
            )

        text, method = self.backend.transcribe_stream(trimmed, sample_rate=self.sample_rate)
        if text.strip():
            self._latest_text = _merge_stream_text(self._latest_text, text)
            self._method = method
        return StreamChunkResult(
            partial=True,
            final=False,
            text=self._latest_text,
            method=self._method,
        )

    def finalize(self) -> tuple[str, str]:
        if self._buffer.size > 0:
            trimmed, _, _ = trim_silence(
                self._buffer,
                sample_rate=self.sample_rate,
                use_webrtc=self.config.speech_vad_enabled,
            )
            if trimmed.size > 0:
                text, method = self.backend.transcribe_stream(trimmed, sample_rate=self.sample_rate)
                if text.strip():
                    self._latest_text = _merge_stream_text(self._latest_text, text)
                    self._method = method
            self._buffer = np.array([], dtype=np.float32)
        return self._latest_text, self._method


class HybridStreamingTranscriber:
    """
    Primary: ViStreamASR U2 streaming (~640ms latency).
    Refine: PhoWhisper on VAD-trimmed audio when hybrid mode is enabled.
    Fallback: faster-whisper chunked streaming when ViStreamASR is unavailable.
    """

    def __init__(self, config: PipelineConfig) -> None:
        self.config = config
        self._vistream_engine = None
        self._phowhisper_pipeline = None
        self._whisper_model = None
        self._vistream_available: bool | None = None

    def diagnostics(self) -> dict[str, object]:
        return {
            "chunk_size_ms": self.config.speech_chunk_size_ms,
            "vad_enabled": self.config.speech_vad_enabled,
            "refine_with_phowhisper": self.config.speech_refine_with_phowhisper,
            "vistream_available": self._check_vistream(),
            "engine_mode": self.config.speech_engine,
        }

    def create_session(self) -> StreamingASRSession:
        return StreamingASRSession(
            config=self.config,
            backend=self,
            sample_rate=self.config.speech_sample_rate,
        )

    def transcribe_stream(self, samples: np.ndarray, *, sample_rate: int) -> tuple[str, str]:
        trimmed, _, _ = trim_silence(
            samples,
            sample_rate=sample_rate,
            use_webrtc=self.config.speech_vad_enabled,
        )
        if trimmed.size == 0:
            return "", "streaming_vad_empty"
        return self.transcribe(trimmed, sample_rate=sample_rate)

    def transcribe(self, samples: np.ndarray, *, sample_rate: int) -> tuple[str, str]:
        trimmed, _, _ = trim_silence(
            samples,
            sample_rate=sample_rate,
            use_webrtc=self.config.speech_vad_enabled,
        )
        if trimmed.size == 0:
            return "", "streaming_vad_empty"

        draft, draft_method = self._streaming_transcribe(trimmed, sample_rate=sample_rate)
        if not self.config.speech_refine_with_phowhisper:
            return draft, draft_method
        if self.config.speech_engine not in {"vistream_phowhisper", "phowhisper"}:
            return draft, draft_method

        try:
            refined, refine_method = self._transcribe_phowhisper(
                trimmed,
                sample_rate=sample_rate,
            )
        except Exception:
            # Keep the draft transcript if PhoWhisper refinement is unavailable.
            return draft, draft_method
        if not refined.strip():
            return draft, draft_method
        if not draft.strip():
            return refined, refine_method
        return refined, f"{draft_method}+{refine_method}"

    def transcribe_wav_bytes(self, wav_bytes: bytes) -> tuple[str, str]:
        from ekyc_document.speech.audio import wav_bytes_to_samples

        samples, sample_rate = wav_bytes_to_samples(wav_bytes)
        return self.transcribe(samples, sample_rate=sample_rate)

    def _streaming_transcribe(self, samples: np.ndarray, *, sample_rate: int) -> tuple[str, str]:
        engine = self.config.speech_engine
        if engine in {"vistream", "vistream_phowhisper"} and self._check_vistream():
            return self._transcribe_vistream(samples, sample_rate=sample_rate)
        if engine == "phowhisper":
            return self._transcribe_phowhisper(samples, sample_rate=sample_rate)
        if engine == "faster-whisper":
            return self._transcribe_faster_whisper(samples, sample_rate=sample_rate)
        return self._transcribe_chunked_faster_whisper(samples, sample_rate=sample_rate)

    def _check_vistream(self) -> bool:
        if self._vistream_available is not None:
            return self._vistream_available
        try:
            import ViStreamASR  # noqa: F401

            self._vistream_available = True
        except ImportError:
            self._vistream_available = False
        return self._vistream_available

    def _transcribe_vistream(self, samples: np.ndarray, *, sample_rate: int) -> tuple[str, str]:
        try:
            from ViStreamASR import ASREngine
        except ImportError as exc:
            raise RuntimeError(
                "Cần cài ViStreamASR: pip install ViStreamASR"
            ) from exc

        if self._vistream_engine is None:
            self._vistream_engine = ASREngine(
                chunk_size_ms=self.config.speech_chunk_size_ms,
                debug_mode=False,
            )
            self._vistream_engine.initialize_models()

        if sample_rate != self.config.speech_sample_rate:
            samples = _resample_linear(samples, sample_rate, self.config.speech_sample_rate)
            sample_rate = self.config.speech_sample_rate

        chunks = chunk_for_streaming(
            samples,
            sample_rate=sample_rate,
            chunk_ms=self.config.speech_chunk_size_ms,
        )
        parts: list[str] = []
        for index, chunk in enumerate(chunks):
            is_last = index == len(chunks) - 1
            result = self._vistream_engine.process_audio(chunk, is_last=is_last)
            text = str(result.get("text", "")).strip() if isinstance(result, dict) else ""
            if text:
                parts.append(text)
        transcript = _merge_stream_text("", " ".join(parts))
        return transcript, f"vistream_u2/{self.config.speech_chunk_size_ms}ms"

    def _transcribe_chunked_faster_whisper(
        self,
        samples: np.ndarray,
        *,
        sample_rate: int,
    ) -> tuple[str, str]:
        """U2-style chunked streaming fallback when ViStreamASR is not installed."""
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError(
                "Cần cài faster-whisper hoặc ViStreamASR cho streaming ASR."
            ) from exc

        if self._whisper_model is None:
            device = "cuda" if self.config.use_gpu else "cpu"
            compute_type = "float16" if self.config.use_gpu else "int8"
            self._whisper_model = WhisperModel(
                self.config.whisper_model_size,
                device=device,
                compute_type=compute_type,
                download_root=str(self.config.models_dir / "whisper"),
            )

        chunks = chunk_for_streaming(
            samples,
            sample_rate=sample_rate,
            chunk_ms=self.config.speech_chunk_size_ms,
        )
        parts: list[str] = []
        for chunk in chunks:
            if float(np.sqrt(np.mean(chunk**2))) < 0.003:
                continue
            segments, _ = self._whisper_model.transcribe(
                chunk,
                language="vi",
                beam_size=3,
                vad_filter=False,
            )
            text = " ".join(item.text.strip() for item in segments if item.text.strip())
            if text:
                parts.append(text)

        if not parts:
            segments, _ = self._whisper_model.transcribe(
                samples,
                language="vi",
                beam_size=5,
                vad_filter=True,
            )
            transcript = " ".join(item.text.strip() for item in segments if item.text.strip())
            return transcript, f"faster-whisper-stream/{self.config.whisper_model_size}"

        transcript = _merge_stream_text("", " ".join(parts))
        return transcript, f"faster-whisper-chunk/{self.config.speech_chunk_size_ms}ms"

    def _transcribe_faster_whisper(self, samples: np.ndarray, *, sample_rate: int) -> tuple[str, str]:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError("Cần cài faster-whisper.") from exc

        if self._whisper_model is None:
            device = "cuda" if self.config.use_gpu else "cpu"
            compute_type = "float16" if self.config.use_gpu else "int8"
            self._whisper_model = WhisperModel(
                self.config.whisper_model_size,
                device=device,
                compute_type=compute_type,
                download_root=str(self.config.models_dir / "whisper"),
            )

        segments, _ = self._whisper_model.transcribe(
            samples,
            language="vi",
            beam_size=5,
            vad_filter=True,
        )
        transcript = " ".join(item.text.strip() for item in segments if item.text.strip())
        return transcript, f"faster-whisper/{self.config.whisper_model_size}"

    def _transcribe_phowhisper(self, samples: np.ndarray, *, sample_rate: int) -> tuple[str, str]:
        try:
            from transformers import pipeline
        except ImportError as exc:
            raise RuntimeError("Cần cài transformers cho PhoWhisper.") from exc

        if self._phowhisper_pipeline is None:
            device = 0 if self.config.use_gpu else -1
            self._phowhisper_pipeline = pipeline(
                "automatic-speech-recognition",
                model=self.config.phowhisper_model,
                device=device,
            )

        result = self._phowhisper_pipeline(
            {"raw": np.asarray(samples, dtype=np.float32), "sampling_rate": sample_rate},
        )
        if isinstance(result, dict):
            transcript = str(result.get("text", "")).strip()
        else:
            transcript = str(result).strip()
        model_name = self.config.phowhisper_model.rsplit("/", maxsplit=1)[-1]
        return transcript, f"phowhisper/{model_name}"


def _merge_stream_text(previous: str, incoming: str) -> str:
    incoming = incoming.strip()
    if not incoming:
        return previous.strip()
    if not previous.strip():
        return incoming
    if incoming.startswith(previous):
        return incoming
    if previous in incoming:
        return incoming
    return f"{previous} {incoming}".strip()


def _resample_linear(samples: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    if src_rate == dst_rate or samples.size == 0:
        return samples
    duration = samples.size / src_rate
    dst_len = max(1, int(duration * dst_rate))
    src_x = np.linspace(0.0, 1.0, samples.size, endpoint=False)
    dst_x = np.linspace(0.0, 1.0, dst_len, endpoint=False)
    return np.interp(dst_x, src_x, samples).astype(np.float32)
