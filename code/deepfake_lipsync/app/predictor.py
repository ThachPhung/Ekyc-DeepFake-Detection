"""SyncNet lip-sync analysis with Hugging Face weights."""

from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from syncnet_python import SyncNetPipeline

from app.schemas import LipSyncResponse

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SyncNetSettings:
    s3fd_weights: Path
    syncnet_weights: Path
    device: str = "cpu"
    min_track: int = 30
    min_dist_real_max: float = 7.0
    confidence_real_min: float = 3.5
    max_offset_frames: int = 3
    min_dist_fake_min: float = 9.5
    confidence_fake_max: float = 2.0

    @classmethod
    def from_env(cls) -> SyncNetSettings:
        return cls(
            s3fd_weights=Path(os.getenv("S3FD_WEIGHTS", "/app/weights/sfd_face.pth")),
            syncnet_weights=Path(os.getenv("SYNCNET_WEIGHTS", "/app/weights/syncnet_v2.model")),
            device=os.getenv("DEVICE", "cpu"),
            min_track=int(os.getenv("SYNCNET_MIN_TRACK", "30")),
            min_dist_real_max=float(os.getenv("SYNCNET_MIN_DIST_REAL_MAX", "7.0")),
            confidence_real_min=float(os.getenv("SYNCNET_CONFIDENCE_REAL_MIN", "3.5")),
            max_offset_frames=int(os.getenv("SYNCNET_MAX_OFFSET_FRAMES", "3")),
            min_dist_fake_min=float(os.getenv("SYNCNET_MIN_DIST_FAKE_MIN", "9.5")),
            confidence_fake_max=float(os.getenv("SYNCNET_CONFIDENCE_FAKE_MAX", "2.0")),
        )


class SyncNetPredictor:
    def __init__(self, settings: SyncNetSettings) -> None:
        self.settings = settings
        if not settings.s3fd_weights.is_file():
            raise FileNotFoundError(f"S3FD weights missing: {settings.s3fd_weights}")
        if not settings.syncnet_weights.is_file():
            raise FileNotFoundError(f"SyncNet weights missing: {settings.syncnet_weights}")

        logger.info(
            "Loading SyncNetPipeline device=%s s3fd=%s syncnet=%s min_track=%d",
            settings.device,
            settings.s3fd_weights,
            settings.syncnet_weights,
            settings.min_track,
        )
        self.pipeline = SyncNetPipeline(
            device=settings.device,
            s3fd_weights=str(settings.s3fd_weights),
            syncnet_weights=str(settings.syncnet_weights),
            min_track=settings.min_track,
        )

    def predict_video_bytes(self, video_bytes: bytes, *, suffix: str = ".webm") -> LipSyncResponse:
        if not video_bytes:
            raise ValueError("Video file is empty.")

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(video_bytes)
            video_path = tmp.name

        try:
            (
                offset_list,
                confidence_list,
                min_dist_list,
                _best_confidence,
                _best_min_dist,
                _detections_json,
                success,
            ) = self.pipeline.inference(video_path=video_path, audio_path=None)

            if not success or not offset_list:
                return LipSyncResponse(
                    verdict="uncertain",
                    is_real=False,
                    is_fake=False,
                    confidence=0.0,
                    manipulation_probability=0.5,
                    face_detected=False,
                    detail="Không phát hiện track khuôn mặt/âm thanh đủ dài để phân tích lip-sync.",
                )

            offset = int(offset_list[0])
            sync_confidence = float(confidence_list[0])
            min_distance = float(min_dist_list[0])
            return _to_lipsync_response(
                offset=offset,
                sync_confidence=sync_confidence,
                min_distance=min_distance,
                settings=self.settings,
            )
        finally:
            Path(video_path).unlink(missing_ok=True)


def _to_lipsync_response(
    *,
    offset: int,
    sync_confidence: float,
    min_distance: float,
    settings: SyncNetSettings,
) -> LipSyncResponse:
    # authenticity_confidence: cao khi lip-sync tốt
    authenticity = _clip01(sync_confidence / 12.0)
    manipulation = _clip01((min_distance - 4.0) / 10.0)
    manipulation = _clip01(max(manipulation, 1.0 - authenticity))

    looks_real = (
        min_distance <= settings.min_dist_real_max
        and sync_confidence >= settings.confidence_real_min
        and abs(offset) <= settings.max_offset_frames
    )
    looks_fake = (
        min_distance >= settings.min_dist_fake_min
        or sync_confidence <= settings.confidence_fake_max
        or abs(offset) >= settings.max_offset_frames + 3
    )

    if looks_real and not looks_fake:
        verdict = "real"
        is_fake = False
        is_real = True
    elif looks_fake and not looks_real:
        verdict = "fake"
        is_fake = True
        is_real = False
    else:
        verdict = "uncertain"
        is_fake = False
        is_real = False

    return LipSyncResponse(
        verdict=verdict,
        is_real=is_real,
        is_fake=is_fake,
        confidence=round(authenticity, 4),
        manipulation_probability=round(manipulation, 4),
        av_offset_frames=offset,
        min_distance=round(min_distance, 4),
        sync_confidence=round(sync_confidence, 4),
        face_detected=True,
        detail=(
            f"SyncNet offset={offset} frames, min_dist={min_distance:.3f}, "
            f"confidence={sync_confidence:.3f}"
        ),
    )


def _clip01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
