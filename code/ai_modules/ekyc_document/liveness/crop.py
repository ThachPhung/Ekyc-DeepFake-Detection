"""MiniFASNet face crop preprocessing (scale 2.7 from bbox center -> 80x80)."""

from __future__ import annotations

import cv2
import numpy as np


def crop_face_minifasnet(
    image_bgr: np.ndarray,
    bbox: list[int],
    *,
    scale: float = 2.7,
    out_size: tuple[int, int] = (80, 80),
) -> np.ndarray:
    """
    Match yakhyo/face-anti-spoofing MiniFASNet crop:
    expand bbox from center by `scale` (default 2.7), then resize to 80x80.
    """
    src_h, src_w = image_bgr.shape[:2]
    x, y, box_w, box_h = bbox
    if box_w <= 0 or box_h <= 0:
        return cv2.resize(image_bgr, out_size)

    crop_scale = min((src_h - 1) / box_h, (src_w - 1) / box_w, scale)
    new_w = box_w * crop_scale
    new_h = box_h * crop_scale
    center_x = x + box_w / 2.0
    center_y = y + box_h / 2.0
    x1 = max(0, int(center_x - new_w / 2.0))
    y1 = max(0, int(center_y - new_h / 2.0))
    x2 = min(src_w - 1, int(center_x + new_w / 2.0))
    y2 = min(src_h - 1, int(center_y + new_h / 2.0))
    cropped = image_bgr[y1 : y2 + 1, x1 : x2 + 1]
    if cropped.size == 0:
        cropped = image_bgr[y : y + box_h, x : x + box_w]
    return cv2.resize(cropped, out_size)


def to_minifasnet_tensor(image_bgr: np.ndarray) -> np.ndarray:
    """MiniFASNet ONNX expects BGR float32 in [0, 255], NCHW."""
    return np.transpose(image_bgr.astype(np.float32), (2, 0, 1))[None, ...]


def minifasnet_live_score(probs: np.ndarray) -> float:
    """MiniFASNetV2 3-class layout: index 1 = Real/live."""
    if probs.size >= 3:
        return float(probs[1])
    if probs.size == 2:
        return float(probs[1])
    return float(probs[0])
