"""5-point landmark alignment for ArcFace / InsightFace recognition."""

from __future__ import annotations

import cv2
import numpy as np

# Standard ArcFace reference landmarks (112x112), InsightFace `face_align` convention.
ARCFACE_REFERENCE_5PT_112: np.ndarray = np.array(
    [
        [38.2946, 51.6963],
        [73.5318, 51.5014],
        [56.0252, 71.7366],
        [41.5493, 92.3655],
        [70.7299, 92.2041],
    ],
    dtype=np.float32,
)


def require_landmarks_5(landmarks: np.ndarray | None) -> np.ndarray | None:
    if landmarks is None:
        return None
    points = np.asarray(landmarks, dtype=np.float32).reshape(-1, 2)
    if points.shape[0] < 5:
        return None
    return points[:5]


def align_face_5pt(
    image_bgr: np.ndarray,
    landmarks: np.ndarray,
    *,
    image_size: int = 112,
) -> np.ndarray:
    """Warp face crop using similarity transform from 5 landmarks."""
    source = require_landmarks_5(landmarks)
    if source is None:
        raise ValueError("Cần đủ 5 điểm landmark để căn chỉnh khuôn mặt.")

    scale = float(image_size) / 112.0
    reference = ARCFACE_REFERENCE_5PT_112 * scale
    matrix, _ = cv2.estimateAffinePartial2D(source, reference, method=cv2.LMEDS)
    if matrix is None:
        matrix = cv2.getAffineTransform(source[:3], reference[:3])

    aligned = cv2.warpAffine(
        image_bgr,
        matrix,
        (image_size, image_size),
        borderValue=0,
    )
    return aligned


def align_face_insightface(image_bgr: np.ndarray, landmarks: np.ndarray, *, image_size: int = 112) -> np.ndarray:
    """Prefer InsightFace helper when available; fall back to OpenCV warp."""
    source = require_landmarks_5(landmarks)
    if source is None:
        raise ValueError("Cần đủ 5 điểm landmark để căn chỉnh khuôn mặt.")
    try:
        from insightface.utils import face_align

        return face_align.norm_crop(image_bgr, landmark=source, image_size=image_size)
    except Exception:
        return align_face_5pt(image_bgr, source, image_size=image_size)
