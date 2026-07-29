"""Shared InsightFace FaceAnalysis bootstrap (SCRFD + ArcFace)."""

from __future__ import annotations

from ekyc_document.config import PipelineConfig
from ekyc_document.face_matching.arcface import resolve_insightface_model


def create_face_analysis(config: PipelineConfig | None = None):
    config = config or PipelineConfig()
    if config.face_detector == "opencv":
        return "opencv"

    from insightface.app import FaceAnalysis

    model_name = resolve_insightface_model(
        config.insightface_model,
        profile=config.insightface_profile,
    )
    providers = (
        ["CUDAExecutionProvider", "CPUExecutionProvider"]
        if config.use_gpu
        else ["CPUExecutionProvider"]
    )
    # SCRFD detection + ArcFace recognition; alignment uses 5-point landmarks internally.
    app = FaceAnalysis(
        name=model_name,
        root=str(config.models_dir),
        providers=providers,
        allowed_modules=["detection", "recognition"],
    )
    det_w, det_h = config.insightface_det_size
    app.prepare(
        ctx_id=0 if config.use_gpu else -1,
        det_size=(det_w, det_h),
        det_thresh=config.insightface_det_thresh,
    )
    return app
