"""Client/server best-frame selection helpers for video liveness."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class FrameFaceLike(Protocol):
    frame_index: int
    quality_score: float


@dataclass(frozen=True)
class ClientFrameMetric:
    frame_index: int
    score: float
    blur: float | None = None
    pose: float | None = None
    eye_openness: float | None = None
    progress: float | None = None


def parse_client_frame_metrics(raw: object) -> list[ClientFrameMetric]:
    if not isinstance(raw, list):
        return []

    metrics: list[ClientFrameMetric] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            frame_index = int(item.get("frame_index", item.get("frameIndex", -1)))
            score = float(item.get("score", 0.0))
        except (TypeError, ValueError):
            continue
        if frame_index < 0:
            continue
        metrics.append(
            ClientFrameMetric(
                frame_index=frame_index,
                score=score,
                blur=_optional_float(item.get("blur")),
                pose=_optional_float(item.get("pose")),
                eye_openness=_optional_float(
                    item.get("eye_openness", item.get("eyeOpenness"))
                ),
                progress=_optional_float(item.get("progress")),
            )
        )
    return metrics


def select_best_frame_face(
    frame_faces: list[FrameFaceLike],
    *,
    client_best_frame_index: int | None = None,
    client_best_frame_progress: float | None = None,
    client_metrics: list[ClientFrameMetric] | None = None,
) -> FrameFaceLike:
    if not frame_faces:
        raise ValueError("frame_faces must not be empty")

    by_index = {item.frame_index: item for item in frame_faces}

    if client_best_frame_progress is not None:
        mapped = _map_progress_to_frame(by_index, client_best_frame_progress)
        if mapped is not None:
            return mapped

    if client_best_frame_index is not None and client_best_frame_index in by_index:
        return by_index[client_best_frame_index]

    if client_metrics:
        progress_ranked = [
            metric for metric in client_metrics if metric.progress is not None
        ]
        if progress_ranked:
            for metric in sorted(progress_ranked, key=lambda item: item.score, reverse=True):
                mapped = _map_progress_to_frame(by_index, metric.progress or 0.0)
                if mapped is not None:
                    return mapped

        ranked = sorted(client_metrics, key=lambda item: item.score, reverse=True)
        for metric in ranked:
            candidate = by_index.get(metric.frame_index)
            if candidate is not None:
                return candidate

    return max(frame_faces, key=lambda item: item.quality_score)


def _map_progress_to_frame(
    by_index: dict[int, FrameFaceLike],
    progress: float,
) -> FrameFaceLike | None:
    if not by_index:
        return None

    indices = sorted(by_index.keys())
    max_idx = indices[-1]
    target_idx = round(_clip01(progress) * max_idx)
    nearest_idx = min(indices, key=lambda item: abs(item - target_idx))
    return by_index[nearest_idx]


def _clip01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
