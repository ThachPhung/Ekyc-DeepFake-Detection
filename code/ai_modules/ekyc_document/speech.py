"""Backward-compatible re-exports for speech verification."""

from ekyc_document.speech.audio import (
    analyze_audio_wav,
    convert_audio_to_wav,
    extract_audio_from_video,
    shutil_which,
)
from ekyc_document.speech.text_utils import (
    digits_to_vietnamese_words,
    normalize_vietnamese_text,
    token_overlap_similarity,
    voice_decision_from_wer,
    word_error_rate,
)
from ekyc_document.speech.verifier import SpeechVerifier

__all__ = [
    "SpeechVerifier",
    "analyze_audio_wav",
    "convert_audio_to_wav",
    "digits_to_vietnamese_words",
    "extract_audio_from_video",
    "normalize_vietnamese_text",
    "shutil_which",
    "token_overlap_similarity",
    "voice_decision_from_wer",
    "word_error_rate",
]
