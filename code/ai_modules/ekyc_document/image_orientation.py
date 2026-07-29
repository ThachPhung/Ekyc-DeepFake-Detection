"""Auto-orient document photos (portrait → landscape) before OCR."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from ekyc_document.document_preprocess import _resize_long_side
from ekyc_document.ocr import OCREngine, OCRResult
from ekyc_document.parser import detect_document_type


@dataclass(frozen=True)
class OrientResult:
    image: np.ndarray
    rotation_degrees: int
    auto_rotated: bool
    warning: str | None = None


_ORIENTATION_KEYWORDS = (
    "CAN CUOC",
    "CONG DAN",
    "CITIZEN",
    "IDENTITY",
    "HO VA TEN",
    "FULL NAME",
    "NGAY SINH",
    "DATE OF BIRTH",
    "QUOC TICH",
    "QUE QUAN",
    "THUONG TRU",
    "PLACE OF ORIGIN",
    "PLACE OF RESIDENCE",
)


def load_bgr_with_exif(source: str | Path) -> np.ndarray:
    """Load image and apply EXIF orientation when present."""
    path = Path(source)
    try:
        from PIL import Image, ImageOps

        with Image.open(path) as pil_image:
            pil_image = ImageOps.exif_transpose(pil_image)
            rgb = np.array(pil_image.convert("RGB"))
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    except Exception:
        image = cv2.imread(str(path))
        if image is None:
            raise ValueError(f"Cannot read image: {path}")
        return image


def is_portrait(image: np.ndarray, *, min_ratio: float = 1.05) -> bool:
    height, width = image.shape[:2]
    return height > width * min_ratio


def is_landscape(image: np.ndarray, *, min_ratio: float = 1.05) -> bool:
    height, width = image.shape[:2]
    return width > height * min_ratio


def rotate_bgr(image: np.ndarray, degrees: int) -> np.ndarray:
    normalized = degrees % 360
    if normalized == 0:
        return image
    if normalized == 90:
        return cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
    if normalized == 180:
        return cv2.rotate(image, cv2.ROTATE_180)
    if normalized == 270:
        return cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
    raise ValueError(f"Unsupported rotation: {degrees}")


def score_orientation_ocr(ocr_result: OCRResult) -> float:
    text = ocr_result.raw_text.strip()
    if not text:
        return 0.0

    score = ocr_result.confidence * 5.0
    score += min(len(ocr_result.lines), 40) * 0.2

    doc_type = detect_document_type(text)
    if doc_type == "CCCD":
        score += 8.0
    elif doc_type != "UNKNOWN":
        score += 4.0

    if re.search(r"(?<!\d)(\d{12})(?!\d)", text.replace(" ", "")):
        score += 6.0

    ascii_text = _normalize_ascii(text)
    score += sum(1.5 for keyword in _ORIENTATION_KEYWORDS if keyword in ascii_text)
    return score


def auto_orient_document(
    image: np.ndarray,
    ocr_engine: OCREngine,
    *,
    portrait_ratio: float = 1.05,
    probe_max_side: int = 1600,
    score_margin: float = 1.0,
) -> OrientResult:
    """
    Rotate portrait CCCD photos to landscape for OCR.

    When height > width, probe OCR on both 90° directions and pick the best score.
    """
    if not is_portrait(image, min_ratio=portrait_ratio):
        return OrientResult(image=image, rotation_degrees=0, auto_rotated=False)

    candidates = (
        (90, rotate_bgr(image, 90)),
        (270, rotate_bgr(image, 270)),
    )

    best_degrees = 0
    best_image = image
    best_score = -1.0

    for degrees, rotated in candidates:
        probe = _resize_long_side(rotated, max_side=probe_max_side)
        ocr_result = ocr_engine.run(probe)
        score = score_orientation_ocr(ocr_result)
        if is_landscape(rotated):
            score += 1.0
        if score > best_score + score_margin or (
            score >= best_score - score_margin and degrees == 90
        ):
            best_score = score
            best_degrees = degrees
            best_image = rotated

    if best_degrees == 0 or best_score <= 0:
        fallback = rotate_bgr(image, 90)
        return OrientResult(
            image=fallback,
            rotation_degrees=90,
            auto_rotated=True,
            warning="Ảnh dọc — đã tự xoay 90° (fallback) trước OCR.",
        )

    return OrientResult(
        image=best_image,
        rotation_degrees=best_degrees,
        auto_rotated=True,
        warning=f"Ảnh dọc — đã tự xoay {best_degrees}° trước OCR.",
    )


def _normalize_ascii(text: str) -> str:
    text = text.replace("Đ", "D").replace("đ", "d")
    without_accents = unicodedata.normalize("NFKD", text)
    ascii_text = "".join(ch for ch in without_accents if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", ascii_text.upper().strip())
