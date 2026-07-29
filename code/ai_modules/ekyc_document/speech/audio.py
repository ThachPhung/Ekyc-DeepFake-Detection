"""Audio extraction and in-memory PCM helpers (ffmpeg pipe, no temp wav for STT)."""

from __future__ import annotations

import io
import subprocess
import wave
from pathlib import Path

import numpy as np


def shutil_which(command: str) -> str | None:
    from shutil import which

    return which(command)


def extract_audio_from_video(
    video_bytes: bytes,
    *,
    sample_rate: int = 16000,
) -> tuple[bytes | None, list[str]]:
    warnings: list[str] = []
    if not video_bytes:
        return None, ["Video rỗng, không thể trích audio."]
    if shutil_which("ffmpeg") is None:
        return None, ["Không tìm thấy ffmpeg trong PATH."]

    completed = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            "pipe:0",
            "-vn",
            "-acodec",
            "pcm_s16le",
            "-ar",
            str(sample_rate),
            "-ac",
            "1",
            "-f",
            "wav",
            "pipe:1",
        ],
        input=video_bytes,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        stderr = (completed.stderr or b"").decode("utf-8", errors="replace").strip()
        if "does not contain any stream" in stderr or "Output file is empty" in stderr:
            warnings.append("Video không có audio track.")
        else:
            warnings.append("ffmpeg không trích được audio từ video.")
        return None, warnings
    if len(completed.stdout) <= 44:
        warnings.append("Audio trích ra rỗng.")
        return None, warnings
    return completed.stdout, warnings


def convert_audio_to_wav(
    audio_bytes: bytes,
    *,
    sample_rate: int = 16000,
) -> tuple[bytes | None, list[str]]:
    if not audio_bytes:
        return None, ["Audio rỗng."]
    if shutil_which("ffmpeg") is None:
        return None, ["Không tìm thấy ffmpeg trong PATH."]

    completed = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            "pipe:0",
            "-acodec",
            "pcm_s16le",
            "-ar",
            str(sample_rate),
            "-ac",
            "1",
            "-f",
            "wav",
            "pipe:1",
        ],
        input=audio_bytes,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0 or len(completed.stdout) <= 44:
        return None, ["ffmpeg không chuyển đổi được file audio."]
    return completed.stdout, []


def wav_bytes_to_samples(wav_bytes: bytes) -> tuple[np.ndarray, int]:
    with wave.open(io.BytesIO(wav_bytes), "rb") as reader:
        sample_width = reader.getsampwidth()
        sample_rate = reader.getframerate()
        raw = reader.readframes(reader.getnframes())

    if not raw:
        return np.array([], dtype=np.float32), sample_rate

    dtype = np.int16 if sample_width == 2 else np.int8
    samples = np.frombuffer(raw, dtype=dtype).astype(np.float32)
    samples /= float(np.iinfo(dtype).max)
    return samples, sample_rate


def samples_to_wav_bytes(samples: np.ndarray, *, sample_rate: int = 16000) -> bytes:
    mono = np.asarray(samples, dtype=np.float32).reshape(-1)
    pcm16 = np.clip(mono * 32768.0, -32768, 32767).astype(np.int16)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(sample_rate)
        writer.writeframes(pcm16.tobytes())
    return buffer.getvalue()


def analyze_audio_samples(samples: np.ndarray, *, sample_rate: int) -> tuple[float, float, float]:
    """Return duration_ms, rms, speech_ratio."""
    if samples.size == 0 or sample_rate <= 0:
        return 0.0, 0.0, 0.0

    mono = np.asarray(samples, dtype=np.float32).reshape(-1)
    duration_ms = round(mono.size / sample_rate * 1000.0, 2)
    rms = round(float(np.sqrt(np.mean(mono**2))), 6)

    frame_size = max(1, int(sample_rate * 0.03))
    energies: list[float] = []
    for start in range(0, mono.size, frame_size):
        chunk = mono[start : start + frame_size]
        if chunk.size == 0:
            continue
        energies.append(float(np.sqrt(np.mean(chunk**2))))
    if not energies:
        return duration_ms, rms, 0.0
    threshold = max(rms * 0.35, 0.003)
    speech_ratio = round(sum(energy >= threshold for energy in energies) / len(energies), 4)
    return duration_ms, rms, speech_ratio


def analyze_audio_wav(wav_bytes: bytes) -> tuple[float, float, float]:
    samples, sample_rate = wav_bytes_to_samples(wav_bytes)
    return analyze_audio_samples(samples, sample_rate=sample_rate)


def pcm16_bytes_to_samples(pcm_bytes: bytes) -> np.ndarray:
    if not pcm_bytes:
        return np.array([], dtype=np.float32)
    pcm16 = np.frombuffer(pcm_bytes, dtype=np.int16)
    return pcm16.astype(np.float32) / 32768.0


def write_temp_wav(samples: np.ndarray, *, sample_rate: int, suffix: str = ".wav") -> Path:
    import tempfile

    handle = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    path = Path(handle.name)
    handle.write(samples_to_wav_bytes(samples, sample_rate=sample_rate))
    handle.close()
    return path
