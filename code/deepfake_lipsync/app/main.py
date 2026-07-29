"""SyncNet lip-sync microservice — compatible with eKYC /api/lip-sync client."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, UploadFile

from app.predictor import SyncNetPredictor, SyncNetSettings
from app.schemas import LipSyncResponse

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

_predictor: SyncNetPredictor | None = None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _predictor
    settings = SyncNetSettings.from_env()
    try:
        _predictor = SyncNetPredictor(settings)
        logger.info("SyncNet lip-sync service ready")
    except FileNotFoundError as exc:
        logger.warning("SyncNet weights not ready: %s", exc)
        _predictor = None
    yield
    _predictor = None


app = FastAPI(
    title="Lip Sync Detection Service",
    description="SyncNet audio-visual lip-sync check (weights from Hugging Face).",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/")
def root() -> dict[str, object]:
    return {
        "service": "Lip Sync Detection Service",
        "engine": "syncnet-python + Hugging Face weights",
        "weights_repo": os.getenv("HF_WEIGHTS_REPO", "lithiumice/syncnet"),
        "predict": "POST /api/lip-sync with multipart video_file",
        "model_loaded": _predictor is not None,
    }


@app.get("/health")
def health() -> dict[str, object]:
    settings = SyncNetSettings.from_env()
    return {
        "status": "ok" if _predictor is not None else "degraded",
        "model_loaded": _predictor is not None,
        "device": settings.device,
        "weights": {
            "s3fd": str(settings.s3fd_weights),
            "syncnet": str(settings.syncnet_weights),
            "s3fd_exists": settings.s3fd_weights.is_file(),
            "syncnet_exists": settings.syncnet_weights.is_file(),
        },
    }


@app.post("/api/lip-sync", response_model=LipSyncResponse)
async def check_lip_sync(video_file: UploadFile = File(...)) -> LipSyncResponse:
    if _predictor is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "Model not loaded. Weights should be baked into the Docker image "
                "via Hugging Face (lithiumice/syncnet)."
            ),
        )

    video_bytes = await video_file.read()
    suffix = ".webm"
    if video_file.filename and "." in video_file.filename:
        suffix = "." + video_file.filename.rsplit(".", 1)[-1].lower()

    try:
        return _predictor.predict_video_bytes(video_bytes, suffix=suffix)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Lip-sync inference failed")
        raise HTTPException(status_code=500, detail="Lip-sync inference failed") from exc
