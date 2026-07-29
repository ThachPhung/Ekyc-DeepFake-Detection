"""Runtime configuration for the eKYC document pipeline."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_env_file() -> None:
    candidates = []
    for env_path in (
        Path.cwd() / ".env",
        Path(__file__).resolve().parents[2] / ".env",
        Path(__file__).resolve().parents[3] / ".env",
    ):
        if env_path not in candidates:
            candidates.append(env_path)
    loaded_any = False
    for env_path in candidates:
        if not env_path.is_file():
            continue
        try:
            from dotenv import load_dotenv

            load_dotenv(env_path, override=False)
        except ImportError:
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key, value = key.strip(), value.strip()
                if key and key not in os.environ:
                    os.environ[key] = value
        loaded_any = True

    if loaded_any:
        return


_load_env_file()

_CODE_DIR = Path(__file__).resolve().parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[3]


def _resolve_project_path(raw: str | None, default: Path) -> Path:
    """Resolve paths from .env relative to repo root, not cwd."""
    if not raw:
        return default
    path = Path(raw)
    if path.is_absolute():
        return path
    return (_REPO_ROOT / path).resolve()


def _parse_float_map(raw: str | None, default: dict[str, float]) -> dict[str, float]:
    if not raw:
        return dict(default)

    values = dict(default)
    for item in raw.split(","):
        key, sep, value = item.partition(":")
        if not sep:
            key, sep, value = item.partition("=")
        key = key.strip()
        if not key:
            continue
        try:
            values[key] = float(value.strip())
        except ValueError:
            continue
    return values


def _optional_model_path(env_name: str, default_relative: str) -> Path | None:
    raw = os.getenv(env_name, "").strip()
    if raw:
        return _resolve_project_path(raw, _CODE_DIR / default_relative)
    candidate = (_CODE_DIR / default_relative).resolve()
    return candidate if candidate.is_file() else None


def _resolve_insightface_model() -> str:
    profile = os.getenv("EKYC_INSIGHTFACE_PROFILE", "").strip().lower()
    if profile in {"speed", "fast", "buffalo_l"}:
        return "buffalo_l"
    if profile in {"accuracy", "accurate", "glintr100", "high"}:
        return "glintr100"
    raw = os.getenv("EKYC_INSIGHTFACE_MODEL", "buffalo_l").strip()
    return raw or "buffalo_l"


@dataclass
class PipelineConfig:
    ocr_engine: str = field(
        default_factory=lambda: os.getenv("EKYC_OCR_ENGINE", "rapidocr_ppocrv6").lower()
    )
    ocr_languages: list[str] = field(default_factory=lambda: ["vi", "en"])
    ocr_preprocess: bool = field(
        default_factory=lambda: os.getenv("EKYC_OCR_PREPROCESS", "true").lower()
        not in {"0", "false", "no"}
    )
    auto_orient_document: bool = field(
        default_factory=lambda: os.getenv("EKYC_AUTO_ORIENT", "true").lower()
        not in {"0", "false", "no"}
    )
    auto_orient_portrait_ratio: float = field(
        default_factory=lambda: float(os.getenv("EKYC_AUTO_ORIENT_PORTRAIT_RATIO", "1.05"))
    )
    auto_orient_probe_max_side: int = field(
        default_factory=lambda: int(os.getenv("EKYC_AUTO_ORIENT_PROBE_MAX_SIDE", "1600"))
    )
    rapidocr_rec_model: str = field(
        default_factory=lambda: os.getenv(
            "EKYC_RAPIDOCR_REC_MODEL",
            "vi",
        )
    )
    rapidocr_lang: str = field(
        default_factory=lambda: os.getenv("EKYC_RAPIDOCR_LANG", "vi")
    )
    prefer_onnx: bool = field(
        default_factory=lambda: os.getenv("EKYC_PREFER_ONNX", "true").lower()
        not in {"0", "false", "no"}
    )
    require_onnx_models: bool = field(
        default_factory=lambda: os.getenv("EKYC_REQUIRE_ONNX_MODELS", "false").lower()
        in {"1", "true", "yes"}
    )
    allow_heuristic_fallback: bool = field(
        default_factory=lambda: os.getenv("EKYC_ALLOW_HEURISTIC_FALLBACK", "true").lower()
        not in {"0", "false", "no"}
    )
    deepfake_preprocess: str = field(
        default_factory=lambda: os.getenv("EKYC_DEEPFAKE_PREPROCESS", "hf_vit").lower()
    )
    deepfake_hf_processor_model: str = field(
        default_factory=lambda: os.getenv(
            "EKYC_DEEPFAKE_HF_PROCESSOR_MODEL",
            "prithivMLmods/Deep-Fake-Detector-v2-Model",
        )
    )
    deepfake_hf_model: str | None = field(
        default_factory=lambda: (
            os.getenv("EKYC_DEEPFAKE_HF_MODEL") or None
            if os.getenv("EKYC_DEEPFAKE_HF_MODEL", "").strip()
            else None
        )
    )
    face_detector: str = field(
        default_factory=lambda: os.getenv("EKYC_FACE_DETECTOR", "insightface").lower()
    )
    insightface_model: str = field(default_factory=_resolve_insightface_model)
    insightface_profile: str | None = field(
        default_factory=lambda: os.getenv("EKYC_INSIGHTFACE_PROFILE") or None
    )
    insightface_det_size: tuple[int, int] = field(
        default_factory=lambda: (
            int(os.getenv("EKYC_INSIGHTFACE_DET_WIDTH", "640")),
            int(os.getenv("EKYC_INSIGHTFACE_DET_HEIGHT", "640")),
        )
    )
    insightface_det_thresh: float = field(
        default_factory=lambda: float(os.getenv("EKYC_INSIGHTFACE_DET_THRESH", "0.5"))
    )
    insightface_align_size: int = field(
        default_factory=lambda: int(os.getenv("EKYC_INSIGHTFACE_ALIGN_SIZE", "112"))
    )
    models_dir: Path = field(
        default_factory=lambda: _resolve_project_path(
            os.getenv("EKYC_MODELS_DIR"),
            _CODE_DIR / "models",
        )
    )
    min_quality_score: float = field(
        default_factory=lambda: float(os.getenv("EKYC_MIN_QUALITY_SCORE", "0.5"))
    )
    min_document_face_confidence: float = field(
        default_factory=lambda: float(
            os.getenv("EKYC_MIN_DOCUMENT_FACE_CONFIDENCE", "0.55")
        )
    )
    use_gpu: bool = field(
        default_factory=lambda: os.getenv("EKYC_USE_GPU", "false").lower() == "true"
    )

    quality_weights: dict[str, float] = field(
        default_factory=lambda: {
            "blur": 0.25,
            "brightness": 0.13,
            "contrast": 0.13,
            "glare": 0.18,
            "corners": 0.21,
            "screenshot": 0.10,
        }
    )
    private_storage_dir: Path = field(
        default_factory=lambda: _resolve_project_path(
            os.getenv("EKYC_PRIVATE_STORAGE_DIR"),
            _CODE_DIR / "data" / "private",
        )
    )
    internal_api_key: str | None = field(
        default_factory=lambda: os.getenv("EKYC_INTERNAL_API_KEY") or None
    )

    # Biometric / face matching thresholds. Tune with production validation data.
    face_match_threshold: float = field(
        default_factory=lambda: float(os.getenv("EKYC_FACE_MATCH_THRESHOLD", "0.45"))
    )
    face_consider_threshold: float = field(
        default_factory=lambda: float(os.getenv("EKYC_FACE_CONSIDER_THRESHOLD", "0.30"))
    )
    min_face_quality_score: float = field(
        default_factory=lambda: float(os.getenv("EKYC_MIN_FACE_QUALITY_SCORE", "0.55"))
    )
    min_liveness_score: float = field(
        default_factory=lambda: float(os.getenv("EKYC_MIN_LIVENESS_SCORE", "0.65"))
    )
    min_manual_liveness_score: float = field(
        default_factory=lambda: float(os.getenv("EKYC_MIN_MANUAL_LIVENESS_SCORE", "0.45"))
    )
    min_face_coverage: float = field(
        default_factory=lambda: float(os.getenv("EKYC_MIN_FACE_COVERAGE", "0.08"))
    )
    max_face_coverage: float = field(
        default_factory=lambda: float(os.getenv("EKYC_MAX_FACE_COVERAGE", "0.65"))
    )
    max_video_frames: int = field(
        default_factory=lambda: int(os.getenv("EKYC_MAX_VIDEO_FRAMES", "90"))
    )
    video_frame_stride: int = field(
        default_factory=lambda: int(os.getenv("EKYC_VIDEO_FRAME_STRIDE", "5"))
    )
    adaptive_video_sampling: bool = field(
        default_factory=lambda: os.getenv("EKYC_ADAPTIVE_VIDEO_SAMPLING", "true").lower()
        not in {"0", "false", "no"}
    )
    target_video_samples: int = field(
        default_factory=lambda: int(os.getenv("EKYC_TARGET_VIDEO_SAMPLES", "36"))
    )
    min_video_face_frames: int = field(
        default_factory=lambda: int(os.getenv("EKYC_MIN_VIDEO_FACE_FRAMES", "8"))
    )
    active_liveness_challenges: list[str] = field(
        default_factory=lambda: [
            item.strip()
            for item in os.getenv(
                "EKYC_ACTIVE_LIVENESS_CHALLENGES",
                "turn_left,turn_right,look_up,look_down,blink",
            ).split(",")
            if item.strip()
        ]
    )
    default_liveness_challenge: str = field(
        default_factory=lambda: os.getenv("EKYC_DEFAULT_LIVENESS_CHALLENGE", "blink")
    )
    skip_active_liveness: bool = field(
        default_factory=lambda: os.getenv("EKYC_SKIP_ACTIVE_LIVENESS", "false").lower()
        not in {"0", "false", "no"}
    )
    minifasnet_onnx_path: Path | None = field(
        default_factory=lambda: (
            _resolve_project_path(os.getenv("EKYC_MINIFASNET_ONNX_PATH"), _CODE_DIR / "models" / "minifasnet.onnx")
            if os.getenv("EKYC_MINIFASNET_ONNX_PATH")
            else _CODE_DIR / "models" / "minifasnet.onnx"
        )
    )
    minifasnet_int8_onnx_path: Path | None = field(
        default_factory=lambda: _optional_model_path(
            "EKYC_MINIFASNET_INT8_ONNX_PATH",
            "models/minifasnet_v2se_int8.onnx",
        )
    )
    minifasnet_crop_scale: float = field(
        default_factory=lambda: float(os.getenv("EKYC_MINIFASNET_CROP_SCALE", "2.7"))
    )
    deepfake_onnx_path: Path | None = field(
        default_factory=lambda: (
            _resolve_project_path(
                os.getenv("EKYC_DEEPFAKE_ONNX_PATH"),
                _CODE_DIR / "models" / "deepfake_detector.onnx",
            )
            if os.getenv("EKYC_DEEPFAKE_ONNX_PATH")
            else _CODE_DIR / "models" / "deepfake_detector.onnx"
        )
    )
    deepfake_suspicious_threshold: float = field(
        default_factory=lambda: float(os.getenv("EKYC_DEEPFAKE_SUSPICIOUS_THRESHOLD", "0.68"))
    )
    identity_drift_threshold: float = field(
        default_factory=lambda: float(os.getenv("EKYC_IDENTITY_DRIFT_THRESHOLD", "0.22"))
    )
    replay_suspicious_threshold: float = field(
        default_factory=lambda: float(os.getenv("EKYC_REPLAY_SUSPICIOUS_THRESHOLD", "0.72"))
    )
    replay_dup_hamming_max: int = field(
        default_factory=lambda: int(os.getenv("EKYC_REPLAY_DUP_HAMMING_MAX", "2"))
    )
    replay_confirm_moire_min: float = field(
        default_factory=lambda: float(os.getenv("EKYC_REPLAY_CONFIRM_MOIRE_MIN", "0.68"))
    )
    replay_confirm_dup_min: float = field(
        default_factory=lambda: float(os.getenv("EKYC_REPLAY_CONFIRM_DUP_MIN", "0.52"))
    )
    replay_frozen_dup_min: float = field(
        default_factory=lambda: float(os.getenv("EKYC_REPLAY_FROZEN_DUP_MIN", "0.82"))
    )
    replay_motion_dup_relief_min: float = field(
        default_factory=lambda: float(os.getenv("EKYC_REPLAY_MOTION_DUP_RELIEF_MIN", "0.28"))
    )
    camera_injection_suspicious_threshold: float = field(
        default_factory=lambda: float(os.getenv("EKYC_CAMERA_INJECTION_SUSPICIOUS_THRESHOLD", "0.65"))
    )
    deepfake_min_suspicious_frames: int = field(
        default_factory=lambda: int(os.getenv("EKYC_DEEPFAKE_MIN_SUSPICIOUS_FRAMES", "2"))
    )
    deepfake_single_frame_block_score: float = field(
        default_factory=lambda: float(
            os.getenv("EKYC_DEEPFAKE_SINGLE_FRAME_BLOCK_SCORE", "0.88")
        )
    )
    lipsync_service_url: str | None = field(
        default_factory=lambda: os.getenv("EKYC_LIPSYNC_SERVICE_URL") or None
    )
    lipsync_enabled: bool = field(
        default_factory=lambda: os.getenv("EKYC_LIPSYNC_ENABLED", "true").lower()
        not in {"0", "false", "no"}
    )
    lipsync_suspicious_threshold: float = field(
        default_factory=lambda: float(os.getenv("EKYC_LIPSYNC_SUSPICIOUS_THRESHOLD", "0.65"))
    )
    lipsync_timeout_seconds: float = field(
        default_factory=lambda: float(os.getenv("EKYC_LIPSYNC_TIMEOUT_SECONDS", "120"))
    )
    risk_liveness_trust_threshold: float = field(
        default_factory=lambda: float(os.getenv("EKYC_RISK_LIVENESS_TRUST_THRESHOLD", "0.88"))
    )
    risk_liveness_trust_dampening: float = field(
        default_factory=lambda: float(os.getenv("EKYC_RISK_LIVENESS_TRUST_DAMPENING", "0.30"))
    )
    video_risk_weights: dict[str, float] = field(
        default_factory=lambda: _parse_float_map(
            os.getenv("EKYC_VIDEO_RISK_WEIGHTS"),
            {
                "deepfake": 0.25,
                "lipsync": 0.15,
                "identity": 0.22,
                "replay": 0.18,
                "camera": 0.10,
                "voice": 0.10,
            },
        )
    )
    video_risk_review_threshold: float = field(
        default_factory=lambda: float(os.getenv("EKYC_VIDEO_RISK_REVIEW_THRESHOLD", "0.45"))
    )
    video_risk_block_threshold: float = field(
        default_factory=lambda: float(os.getenv("EKYC_VIDEO_RISK_BLOCK_THRESHOLD", "0.72"))
    )
    speech_enabled: bool = field(
        default_factory=lambda: os.getenv("EKYC_SPEECH_ENABLED", "true").lower()
        not in {"0", "false", "no"}
    )
    speech_engine: str = field(
        default_factory=lambda: os.getenv("EKYC_SPEECH_ENGINE", "vistream_phowhisper").lower()
    )
    speech_chunk_size_ms: int = field(
        default_factory=lambda: int(os.getenv("EKYC_SPEECH_CHUNK_SIZE_MS", "640"))
    )
    speech_vad_enabled: bool = field(
        default_factory=lambda: os.getenv("EKYC_SPEECH_VAD_ENABLED", "true").lower()
        not in {"0", "false", "no"}
    )
    speech_refine_with_phowhisper: bool = field(
        default_factory=lambda: os.getenv("EKYC_SPEECH_REFINE_PHOWHISPER", "true").lower()
        not in {"0", "false", "no"}
    )
    whisper_model_size: str = field(
        default_factory=lambda: os.getenv("EKYC_WHISPER_MODEL_SIZE", "small")
    )
    phowhisper_model: str = field(
        default_factory=lambda: os.getenv(
            "EKYC_PHOWHISPER_MODEL",
            "vinai/PhoWhisper-small",
        )
    )
    speech_sample_rate: int = field(
        default_factory=lambda: int(os.getenv("EKYC_SPEECH_SAMPLE_RATE", "16000"))
    )
    voice_wer_pass_threshold: float = field(
        default_factory=lambda: float(os.getenv("EKYC_VOICE_WER_PASS_THRESHOLD", "0.25"))
    )
    voice_wer_consider_threshold: float = field(
        default_factory=lambda: float(os.getenv("EKYC_VOICE_WER_CONSIDER_THRESHOLD", "0.40"))
    )
    voice_mismatch_risk_threshold: float = field(
        default_factory=lambda: float(os.getenv("EKYC_VOICE_MISMATCH_RISK_THRESHOLD", "0.40"))
    )
    min_audio_rms: float = field(
        default_factory=lambda: float(os.getenv("EKYC_MIN_AUDIO_RMS", "0.008"))
    )
    min_audio_duration_ms: float = field(
        default_factory=lambda: float(os.getenv("EKYC_MIN_AUDIO_DURATION_MS", "800"))
    )
    min_speech_ratio: float = field(
        default_factory=lambda: float(os.getenv("EKYC_MIN_SPEECH_RATIO", "0.12"))
    )

    # LLM text extraction (OCR raw text → structured fields). Rule parser is fallback only.
    llm_extract_enabled: bool = field(
        default_factory=lambda: os.getenv("EKYC_LLM_EXTRACT", "true").lower()
        not in {"0", "false", "no", "off"}
    )
    llm_extract_mode: str = field(
        default_factory=lambda: os.getenv("EKYC_LLM_MODE", "always").lower()
    )
    llm_provider: str = field(
        default_factory=lambda: os.getenv("EKYC_LLM_PROVIDER", "openai").lower()
    )
    llm_api_key: str | None = field(
        default_factory=lambda: os.getenv("EKYC_LLM_API_KEY") or None
    )
    openai_api_key: str | None = field(
        default_factory=lambda: os.getenv("OPENAI_API_KEY") or None
    )
    deepseek_api_key: str | None = field(
        default_factory=lambda: os.getenv("DEEPSEEK_API_KEY") or None
    )
    gemini_api_key: str | None = field(
        default_factory=lambda: os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or None
    )
    google_api_key: str | None = field(
        default_factory=lambda: os.getenv("GOOGLE_API_KEY") or None
    )
    anthropic_api_key: str | None = field(
        default_factory=lambda: os.getenv("ANTHROPIC_API_KEY") or None
    )
    llm_model: str | None = field(
        default_factory=lambda: os.getenv("EKYC_LLM_MODEL") or None
    )
    llm_base_url: str | None = field(
        default_factory=lambda: os.getenv("EKYC_LLM_BASE_URL") or None
    )
    llm_timeout_seconds: float = field(
        default_factory=lambda: float(os.getenv("EKYC_LLM_TIMEOUT_SECONDS", "45"))
    )
    llm_fallback_min_ocr_confidence: float = field(
        default_factory=lambda: float(os.getenv("EKYC_LLM_FALLBACK_MIN_OCR_CONF", "0.88"))
    )
    llm_review_enabled: bool = field(
        default_factory=lambda: os.getenv("EKYC_LLM_REVIEW", "true").lower()
        not in {"0", "false", "no", "off"}
    )
    llm_admin_review_enabled: bool = field(
        default_factory=lambda: os.getenv("EKYC_LLM_ADMIN_REVIEW", "true").lower()
        not in {"0", "false", "no", "off"}
    )
    llm_admin_review_auto: bool = field(
        default_factory=lambda: os.getenv("EKYC_LLM_ADMIN_REVIEW_AUTO", "true").lower()
        not in {"0", "false", "no", "off"}
    )

    # YOLO + DBNet + VietOCR stack
    document_warp_enabled: bool = field(
        default_factory=lambda: os.getenv("EKYC_DOCUMENT_WARP", "true").lower()
        not in {"0", "false", "no"}
    )
    document_warp_fallback: str = field(
        default_factory=lambda: os.getenv("EKYC_DOCUMENT_WARP_FALLBACK", "contour").lower()
    )
    yolo_layout_model: Path | None = field(
        default_factory=lambda: _optional_model_path(
            "EKYC_YOLO_LAYOUT_MODEL",
            "models/cccd_layout_yolov11.pt",
        )
    )
    use_yolo_layout_pipeline: bool = field(
        default_factory=lambda: os.getenv("EKYC_USE_YOLO_LAYOUT_PIPELINE", "true").lower()
        not in {"0", "false", "no"}
    )
    yolo_layout_confidence: float = field(
        default_factory=lambda: float(os.getenv("EKYC_YOLO_LAYOUT_CONF", "0.35"))
    )
    dbnet_backend: str = field(
        default_factory=lambda: os.getenv("EKYC_DBNET_BACKEND", "paddle").lower()
    )
    vietocr_config_name: str = field(
        default_factory=lambda: os.getenv("EKYC_VIETOCR_CONFIG", "vgg_transformer")
    )
    vietocr_weights: Path | None = field(
        default_factory=lambda: _resolve_project_path(
            os.getenv("EKYC_VIETOCR_WEIGHTS"),
            _CODE_DIR / "models" / "vietocr_vgg_transformer.pth",
        )
        if os.getenv("EKYC_VIETOCR_WEIGHTS", "").strip()
        else None
    )
    ocr_fallback_engine: str = field(
        default_factory=lambda: os.getenv("EKYC_OCR_FALLBACK_ENGINE", "rapidocr_ppocrv6").lower()
    )
