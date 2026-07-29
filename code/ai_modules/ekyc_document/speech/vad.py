"""Voice Activity Detection — trim silence before streaming ASR."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class SpeechSegment:
    start_sample: int
    end_sample: int

    def duration_ms(self, sample_rate: int = 16000) -> float:
        return (self.end_sample - self.start_sample) / sample_rate * 1000.0


def trim_silence(
    samples: np.ndarray,
    *,
    sample_rate: int = 16000,
    frame_ms: int = 30,
    energy_multiplier: float = 2.5,
    min_speech_ms: int = 120,
    padding_ms: int = 80,
    use_webrtc: bool = True,
) -> tuple[np.ndarray, list[SpeechSegment], float]:
    """
    Return VAD-trimmed samples, speech segments, and speech ratio.
    Prefers webrtcvad when installed; falls back to energy VAD.
    """
    if samples.size == 0:
        return samples, [], 0.0

    mono = _ensure_mono_float(samples)
    segments = (
        _webrtc_vad_segments(mono, sample_rate=sample_rate, frame_ms=frame_ms)
        if use_webrtc
        else None
    )
    if segments is None:
        segments = _energy_vad_segments(
            mono,
            sample_rate=sample_rate,
            frame_ms=frame_ms,
            energy_multiplier=energy_multiplier,
            min_speech_ms=min_speech_ms,
        )

    if not segments:
        return mono, [], 0.0

    pad = int(sample_rate * padding_ms / 1000.0)
    min_len = int(sample_rate * min_speech_ms / 1000.0)
    merged = _merge_segments(segments, gap_samples=int(sample_rate * 0.25))
    padded = []
    for seg in merged:
        start = max(0, seg.start_sample - pad)
        end = min(mono.size, seg.end_sample + pad)
        if end - start >= min_len:
            padded.append(SpeechSegment(start, end))

    if not padded:
        return mono, [], 0.0

    chunks = [mono[seg.start_sample : seg.end_sample] for seg in padded]
    trimmed = np.concatenate(chunks)
    speech_samples = sum(seg.end_sample - seg.start_sample for seg in padded)
    speech_ratio = round(speech_samples / max(mono.size, 1), 4)
    return trimmed, padded, speech_ratio


def chunk_for_streaming(
    samples: np.ndarray,
    *,
    sample_rate: int = 16000,
    chunk_ms: int = 640,
) -> list[np.ndarray]:
    """Split float32 mono audio into fixed-size streaming chunks."""
    if samples.size == 0:
        return []
    chunk_size = max(1, int(sample_rate * chunk_ms / 1000.0))
    chunks: list[np.ndarray] = []
    for start in range(0, samples.size, chunk_size):
        chunk = samples[start : start + chunk_size]
        if chunk.size > 0:
            chunks.append(chunk.astype(np.float32, copy=False))
    return chunks


def _ensure_mono_float(samples: np.ndarray) -> np.ndarray:
    arr = np.asarray(samples, dtype=np.float32).reshape(-1)
    if arr.size == 0:
        return arr
    peak = float(np.max(np.abs(arr)))
    if peak > 1.5:
        arr = arr / 32768.0
    elif peak > 1.0:
        arr = arr / peak
    return arr


def _energy_vad_segments(
    samples: np.ndarray,
    *,
    sample_rate: int,
    frame_ms: int,
    energy_multiplier: float,
    min_speech_ms: int,
) -> list[SpeechSegment]:
    frame_size = max(1, int(sample_rate * frame_ms / 1000.0))
    energies: list[float] = []
    for start in range(0, samples.size, frame_size):
        chunk = samples[start : start + frame_size]
        if chunk.size == 0:
            continue
        energies.append(float(np.sqrt(np.mean(chunk**2))))

    if not energies:
        return []

    baseline = float(np.median(energies))
    threshold = max(baseline * energy_multiplier, 0.004)
    min_frames = max(1, int(min_speech_ms / frame_ms))
    segments: list[SpeechSegment] = []
    run_start: int | None = None
    run_len = 0

    for index, energy in enumerate(energies):
        if energy >= threshold:
            if run_start is None:
                run_start = index
            run_len += 1
            continue
        if run_start is not None and run_len >= min_frames:
            start_sample = run_start * frame_size
            end_sample = min(samples.size, index * frame_size)
            segments.append(SpeechSegment(start_sample, end_sample))
        run_start = None
        run_len = 0

    if run_start is not None and run_len >= min_frames:
        segments.append(
            SpeechSegment(run_start * frame_size, samples.size),
        )
    return segments


def _webrtc_vad_segments(
    samples: np.ndarray,
    *,
    sample_rate: int,
    frame_ms: int,
) -> list[SpeechSegment] | None:
    try:
        import webrtcvad
    except ImportError:
        return None

    if sample_rate not in {8000, 16000, 32000, 48000}:
        return None
    if frame_ms not in {10, 20, 30}:
        frame_ms = 30

    pcm16 = np.clip(samples * 32768.0, -32768, 32767).astype(np.int16)
    frame_bytes = int(sample_rate * frame_ms / 1000.0) * 2
    vad = webrtcvad.Vad(2)
    segments: list[SpeechSegment] = []
    run_start: int | None = None

    for index in range(0, len(pcm16) * 2 - frame_bytes + 1, frame_bytes):
        frame = pcm16.tobytes()[index : index + frame_bytes]
        if len(frame) < frame_bytes:
            break
        is_speech = vad.is_speech(frame, sample_rate)
        sample_index = index // 2
        if is_speech:
            if run_start is None:
                run_start = sample_index
            continue
        if run_start is not None:
            segments.append(SpeechSegment(run_start, sample_index))
            run_start = None

    if run_start is not None:
        segments.append(SpeechSegment(run_start, pcm16.size))
    return segments


def _merge_segments(segments: list[SpeechSegment], *, gap_samples: int) -> list[SpeechSegment]:
    if not segments:
        return []
    ordered = sorted(segments, key=lambda item: item.start_sample)
    merged = [ordered[0]]
    for seg in ordered[1:]:
        last = merged[-1]
        if seg.start_sample - last.end_sample <= gap_samples:
            merged[-1] = SpeechSegment(last.start_sample, max(last.end_sample, seg.end_sample))
        else:
            merged.append(seg)
    return merged
