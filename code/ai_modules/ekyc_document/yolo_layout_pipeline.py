"""YOLO layout-first document extraction: detect → crop fields → OCR → LLM input."""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass, field

import cv2
import numpy as np

from ekyc_document.config import PipelineConfig
from ekyc_document.ocr import OCREngine, OCRResult
from ekyc_document.ocr_stack.layout_detect import (
    LayoutField,
    YOLOLayoutDetector,
    is_layout_ocr_field_label,
    normalize_layout_field_label,
)
from ekyc_document.schemas import FaceResult, OCRLine, ParsedFields

PORTRAIT_LABELS = frozenset({"portrait", "face", "photo"})


@dataclass
class LayoutSideExtraction:
    side: str
    layout_fields: list[LayoutField]
    ocr_lines: list[OCRLine] = field(default_factory=list)
    labeled_text: str = ""
    ocr_confidence: float = 0.0
    portrait_crop: np.ndarray | None = None
    portrait_bbox: tuple[int, int, int, int] | None = None
    engine: str = "yolo_layout+rapidocr"


def layout_pipeline_ready(config: PipelineConfig) -> bool:
    if not config.use_yolo_layout_pipeline:
        return False
    model_path = config.yolo_layout_model
    return model_path is not None and model_path.is_file()


def _normalize_label(label: str) -> str:
    return normalize_layout_field_label(label)


def _best_field_map(fields: list[LayoutField]) -> dict[str, LayoutField]:
    best: dict[str, LayoutField] = {}
    for item in fields:
        label = _normalize_label(item.label)
        current = best.get(label)
        if current is None or item.confidence > current.confidence:
            best[label] = LayoutField(
                label=label,
                bbox=item.bbox,
                confidence=item.confidence,
            )
    return best


def _crop(
    image: np.ndarray,
    bbox: tuple[int, int, int, int],
    *,
    pad: int = 4,
    pad_top: int | None = None,
    pad_bottom: int | None = None,
    pad_left: int | None = None,
    pad_right: int | None = None,
) -> np.ndarray:
    h, w = image.shape[:2]
    x1, y1, x2, y2 = bbox
    top = pad_top if pad_top is not None else pad
    bottom = pad_bottom if pad_bottom is not None else pad
    left = pad_left if pad_left is not None else pad
    right = pad_right if pad_right is not None else pad
    x1 = max(0, x1 - left)
    y1 = max(0, y1 - top)
    x2 = min(w, x2 + right)
    y2 = min(h, y2 + bottom)
    if x2 <= x1 or y2 <= y1:
        return image
    return image[y1:y2, x1:x2].copy()


def _crop_field(image: np.ndarray, bbox: tuple[int, int, int, int], field_label: str) -> np.ndarray:
    """Crop a YOLO field region; date fields often need extra space below the label line."""
    if field_label in {"expiry_date", "date_of_birth", "issue_date"}:
        x1, y1, x2, y2 = bbox
        box_h = max(y2 - y1, 1)
        return _crop(
            image,
            bbox,
            pad_top=4,
            pad_left=4,
            pad_right=4,
            pad_bottom=max(56, int(box_h * 1.8)),
        )
    return _crop(image, bbox, pad=4)


def _ocr_crop(ocr: OCREngine, crop: np.ndarray) -> OCRResult:
    if crop.size == 0:
        return OCRResult(lines=[], confidence=0.0, raw_text="", engine=ocr._engine_name)
    return ocr.run(crop)


def extract_layout_side(
    image: np.ndarray,
    *,
    side: str,
    config: PipelineConfig,
    detector: YOLOLayoutDetector,
    ocr: OCREngine,
) -> LayoutSideExtraction:
    layout_fields = detector.detect(image)
    field_map = _best_field_map(layout_fields)

    portrait_crop: np.ndarray | None = None
    portrait_bbox: tuple[int, int, int, int] | None = None
    for label in PORTRAIT_LABELS:
        if label in field_map:
            portrait_bbox = field_map[label].bbox
            portrait_crop = _crop(image, portrait_bbox, pad=8)
            break
    normalized_portrait = _normalize_label("portrait")
    if portrait_crop is None and normalized_portrait in field_map:
        portrait_bbox = field_map[normalized_portrait].bbox
        portrait_crop = _crop(image, portrait_bbox, pad=8)

    lines: list[OCRLine] = []
    confidences: list[float] = []
    labeled_blocks: list[str] = []

    for label, layout_field in sorted(field_map.items()):
        if not is_layout_ocr_field_label(label):
            continue

        crop = _crop_field(image, layout_field.bbox, label)
        ocr_result = _ocr_crop(ocr, crop)
        text = ocr_result.raw_text.strip()
        if not text:
            continue
        lines.extend(ocr_result.lines)
        if ocr_result.confidence > 0:
            confidences.append(ocr_result.confidence)
        labeled_blocks.append(f"[{label.upper()}]\n{text}")

    labeled_text = "\n\n".join(labeled_blocks)
    avg_conf = float(sum(confidences) / len(confidences)) if confidences else 0.0

    return LayoutSideExtraction(
        side=side,
        layout_fields=layout_fields,
        ocr_lines=lines,
        labeled_text=labeled_text,
        ocr_confidence=avg_conf,
        portrait_crop=portrait_crop,
        portrait_bbox=portrait_bbox,
        engine="yolo_layout+rapidocr",
    )


def build_two_sides_llm_text(front: LayoutSideExtraction, back: LayoutSideExtraction) -> str:
    parts = []
    if front.labeled_text.strip():
        parts.append(f"[MAT_TRUOC]\n{front.labeled_text.strip()}")
    if back.labeled_text.strip():
        parts.append(f"[MAT_SAU]\n{back.labeled_text.strip()}")
    return "\n\n".join(parts)


def portrait_to_face_result(
    portrait_crop: np.ndarray | None,
    portrait_bbox: tuple[int, int, int, int] | None,
    *,
    include_crop: bool = False,
    min_confidence: float = 0.55,
) -> FaceResult:
    if portrait_crop is None or portrait_crop.size == 0:
        return FaceResult(detected=False, warnings=["YOLO không detect box portrait."])

    h, w = portrait_crop.shape[:2]
    if h < 20 or w < 20:
        return FaceResult(
            detected=False,
            warnings=["Crop portrait quá nhỏ."],
        )

    crop_base64 = None
    if include_crop:
        ok, encoded = cv2.imencode(".jpg", portrait_crop)
        if ok:
            crop_base64 = base64.b64encode(encoded.tobytes()).decode("ascii")

    x1, y1, x2, y2 = portrait_bbox or (0, 0, w, h)
    return FaceResult(
        detected=True,
        bbox=[x1, y1, x2 - x1, y2 - y1],
        confidence=0.95,
        quality_score=0.9,
        confident=True,
        warnings=["Portrait lấy từ YOLO layout box."],
        crop_base64=crop_base64,
    )


def collect_back_id_search_text(back: LayoutSideExtraction) -> str:
    """Gom mọi text mặt sau để đối chiếu ID (MRZ / id_back dài)."""
    chunks: list[str] = []
    if back.labeled_text.strip():
        chunks.append(back.labeled_text)
    for line in back.ocr_lines:
        if line.text.strip():
            chunks.append(line.text)
    return "\n".join(chunks)


_OCR_DIGIT_FIX = str.maketrans(
    {
        "O": "0",
        "o": "0",
        "D": "0",
        "Q": "0",
        "I": "1",
        "l": "1",
        "|": "1",
        "S": "5",
        "B": "8",
        "Z": "2",
    }
)


def _normalize_id_search_text(text: str) -> str:
    return re.sub(r"\s+", "", text.upper()).translate(_OCR_DIGIT_FIX)


def validate_cccd_two_sides_id(
    front_id: str | None,
    back_raw_text: str,
) -> tuple[bool, list[str]]:
    """True when 12-digit front id is a substring of back MRZ / id_back OCR."""
    if not front_id or not re.fullmatch(r"\d{12}", str(front_id).strip()):
        return False, ["Thiếu số CCCD hợp lệ (12 số) từ mặt trước để đối chiếu mặt sau."]

    front_digits = str(front_id).strip().translate(_OCR_DIGIT_FIX)
    normalized_back = _normalize_id_search_text(back_raw_text)

    if front_digits in normalized_back:
        return True, []

    back_digits_only = re.sub(r"\D", "", normalized_back)
    if front_digits in back_digits_only:
        return True, []

    for match in re.finditer(r"\d{12}", back_digits_only):
        if match.group(0) == front_digits:
            return True, []

    return False, [
        f"Số CCCD mặt trước ({front_id}) không xuất hiện trong MRZ/id mặt sau — có thể không cùng một thẻ."
    ]


def apply_two_sides_field_policy(
    parsed_fields: ParsedFields | None,
    *,
    front_labeled_text: str,
    sides_ok: bool,
    document_type: str = "CCCD",
) -> ParsedFields | None:
    """When front/back mismatch, drop back issue fields and keep expiry from front OCR only."""
    if parsed_fields is None or sides_ok:
        return parsed_fields

    from ekyc_document.parser import merge_two_sides

    front_fields = merge_two_sides(
        front_labeled_text,
        "",
        forced_type=document_type,  # type: ignore[arg-type]
    ).fields

    updated = parsed_fields.model_dump()
    updated["issue_date"] = None
    updated["issue_place"] = None
    updated["expiry_date"] = front_fields.expiry_date
    return ParsedFields(**updated)
