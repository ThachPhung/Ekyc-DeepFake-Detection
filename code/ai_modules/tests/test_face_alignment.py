from __future__ import annotations

import numpy as np

from ekyc_document.face_matching.alignment import align_face_5pt, require_landmarks_5
from ekyc_document.face_matching.arcface import cosine_distance, cosine_similarity


def test_require_landmarks_5_accepts_five_points() -> None:
    landmarks = np.array(
        [[0, 0], [1, 0], [0.5, 0.5], [0.2, 1], [0.8, 1]],
        dtype=np.float32,
    )
    assert require_landmarks_5(landmarks) is not None


def test_align_face_5pt_returns_square_crop() -> None:
    image = np.zeros((200, 200, 3), dtype=np.uint8)
    landmarks = np.array(
        [[60, 70], [140, 70], [100, 110], [70, 150], [130, 150]],
        dtype=np.float32,
    )
    aligned = align_face_5pt(image, landmarks, image_size=112)
    assert aligned.shape == (112, 112, 3)


def test_cosine_distance_complements_similarity() -> None:
    left = np.asarray([1.0, 0.0], dtype=np.float32)
    right = np.asarray([1.0, 0.0], dtype=np.float32)
    assert cosine_similarity(left, right) == 1.0
    assert cosine_distance(left, right) == 0.0
