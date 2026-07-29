"""Vietnamese speech verification package."""

from ekyc_document.speech.audio import (
    analyze_audio_wav,
    convert_audio_to_wav,
    extract_audio_from_video,
    pcm16_bytes_to_samples,
)
from ekyc_document.speech.streaming import HybridStreamingTranscriber, StreamingASRSession
from ekyc_document.speech.text_utils import (
    digits_to_vietnamese_words,
    normalize_vietnamese_text,
    token_overlap_similarity,
    voice_decision_from_wer,
    word_error_rate,
)
from ekyc_document.speech.verifier import SpeechVerifier
from ekyc_document.speech.vad import trim_silence

__all__ = [
    "HybridStreamingTranscriber",
    "SpeechVerifier",
    "StreamingASRSession",
    "analyze_audio_wav",
    "convert_audio_to_wav",
    "digits_to_vietnamese_words",
    "extract_audio_from_video",
    "normalize_vietnamese_text",
    "pcm16_bytes_to_samples",
    "token_overlap_similarity",
    "trim_silence",
    "voice_decision_from_wer",
    "word_error_rate",
]
