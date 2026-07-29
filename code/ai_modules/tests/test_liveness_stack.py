from __future__ import annotations

import numpy as np

from ekyc_document.biometric import BiometricFace, FrameFace
from ekyc_document.config import PipelineConfig
from ekyc_document.liveness.frame_selection import (
    ClientFrameMetric,
    parse_client_frame_metrics,
    select_best_frame_face,
)
from ekyc_document.liveness.minifasnet import MiniFASNetAntiSpoof
from ekyc_document.schemas import FaceQualityDetail


def _frame_face(frame_index: int, quality_score: float) -> FrameFace:
    return FrameFace(
        frame_index=frame_index,
        face=BiometricFace(
            bbox=[10, 10, 90, 90],
            confidence=0.99,
            face_count=1,
            embedding=None,
            crop=np.zeros((80, 80, 3), dtype=np.uint8),
        ),
        quality_score=quality_score,
        quality=FaceQualityDetail(
            blur=quality_score,
            pose=quality_score,
            illumination=quality_score,
            face_coverage=quality_score,
            centered=quality_score,
        ),
    )


def test_parse_client_frame_metrics_accepts_camel_case() -> None:
    metrics = parse_client_frame_metrics(
        [
            {
                "frameIndex": 3,
                "score": 0.91,
                "blur": 0.8,
                "eyeOpenness": 0.95,
                "progress": 0.42,
            }
        ]
    )

    assert len(metrics) == 1
    assert metrics[0].frame_index == 3
    assert metrics[0].eye_openness == 0.95
    assert metrics[0].progress == 0.42


def test_select_best_frame_face_prefers_client_progress() -> None:
    frames = [_frame_face(0, 0.5), _frame_face(10, 0.6), _frame_face(20, 0.95)]

    best = select_best_frame_face(
        frames,
        client_best_frame_progress=0.5,
    )

    assert best.frame_index == 10


def test_select_best_frame_face_uses_client_metric_ranking() -> None:
    frames = [_frame_face(0, 0.4), _frame_face(5, 0.5), _frame_face(10, 0.6)]
    metrics = [
        ClientFrameMetric(frame_index=99, score=0.2, progress=0.1),
        ClientFrameMetric(frame_index=98, score=0.99, progress=0.95),
    ]

    best = select_best_frame_face(frames, client_metrics=metrics)

    assert best.frame_index == 10


def test_select_best_frame_face_falls_back_to_server_quality() -> None:
    frames = [_frame_face(0, 0.4), _frame_face(5, 0.92), _frame_face(10, 0.5)]

    best = select_best_frame_face(frames)

    assert best.frame_index == 5


def test_minifasnet_diagnostics_reports_active_model(tmp_path) -> None:
    fp32_path = tmp_path / "minifasnet.onnx"
    fp32_path.write_bytes(b"onnx")
    config = PipelineConfig(
        minifasnet_onnx_path=fp32_path,
        minifasnet_int8_onnx_path=tmp_path / "missing_int8.onnx",
    )

    diagnostics = MiniFASNetAntiSpoof(config).diagnostics()

    assert diagnostics["active_model"] == str(fp32_path)
    assert diagnostics["threshold"] == config.min_liveness_score
