"""Document image preprocessing to improve OCR quality."""

from __future__ import annotations

import cv2
import numpy as np


def preprocess_for_ocr(image_bgr: np.ndarray, *, max_side: int = 2200) -> np.ndarray:
    """Enhance document image before OCR: resize, denoise, CLAHE, mild sharpen."""
    if image_bgr is None or image_bgr.size == 0:
        return image_bgr

    working = _resize_long_side(image_bgr, max_side=max_side)
    denoised = cv2.fastNlMeansDenoisingColored(working, None, 5, 5, 7, 21)
    lab = cv2.cvtColor(denoised, cv2.COLOR_BGR2LAB)
    l_channel, a_channel, b_channel = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.2, tileGridSize=(8, 8))
    l_channel = clahe.apply(l_channel)
    enhanced = cv2.merge((l_channel, a_channel, b_channel))
    enhanced = cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)

    blur = cv2.GaussianBlur(enhanced, (0, 0), sigmaX=1.0)
    sharpened = cv2.addWeighted(enhanced, 1.25, blur, -0.25, 0)
    return sharpened


def _resize_long_side(image_bgr: np.ndarray, *, max_side: int) -> np.ndarray:
    height, width = image_bgr.shape[:2]
    long_side = max(height, width)
    if long_side <= max_side:
        return image_bgr
    scale = max_side / float(long_side)
    new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
    return cv2.resize(image_bgr, new_size, interpolation=cv2.INTER_AREA)
