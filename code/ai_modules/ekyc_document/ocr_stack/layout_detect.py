"""Layout detection with YOLOv10 field regions for CCCD."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ekyc_document.config import PipelineConfig


@dataclass(frozen=True)
class LayoutField:
    label: str
    bbox: tuple[int, int, int, int]
    confidence: float


# Raw class names from cccd_layout_yolov11.pt (Roboflow / custom train).
YOLO_LAYOUT_CLASS_NAMES = (
    "address",
    "birthday",
    "birthplace",
    "bottom_left",
    "bottom_right",
    "expiry",
    "feature",
    "gender",
    "id",
    "id_back",
    "issue_date",
    "name",
    "nationality",
    "new_back_cccd",
    "new_front_cccd",
    "old_back_cccd",
    "old_front_cccd",
    "portrait",
    "top_left",
    "top_right",
)

# Canonical OCR/LLM field keys used inside the pipeline.
LAYOUT_TEXT_FIELD_LABELS = frozenset(
    {
        "id_number",
        "full_name",
        "date_of_birth",
        "sex",
        "nationality",
        "place_of_origin",
        "place_of_residence",
        "issue_date",
        "issue_place",
        "expiry_date",
        "mrz",
    }
)

# YOLO raw label -> canonical field key.
LAYOUT_FIELD_ALIASES: dict[str, str] = {
    "id": "id_number",
    "name": "full_name",
    "birthday": "date_of_birth",
    "gender": "sex",
    "address": "place_of_residence",
    "birthplace": "place_of_origin",
    "expiry": "expiry_date",
    "id_back": "mrz",
    "nationality": "nationality",
    "issue_date": "issue_date",
    "portrait": "portrait",
    "id_number": "id_number",
    "full_name": "full_name",
    "date_of_birth": "date_of_birth",
    "sex": "sex",
    "place_of_origin": "place_of_origin",
    "place_of_residence": "place_of_residence",
    "issue_place": "issue_place",
    "expiry_date": "expiry_date",
    "mrz": "mrz",
}

# Regions detected by YOLO but never sent to field OCR.
LAYOUT_SKIP_LABELS = frozenset(
    {
        "feature",
        "new_back_cccd",
        "new_front_cccd",
        "old_back_cccd",
        "old_front_cccd",
        "cccd_card",
    }
)

PORTRAIT_LAYOUT_LABELS = frozenset({"portrait", "face", "photo"})

# Backward-compatible alias used in docs/diagnostics.
CCCD_LAYOUT_LABELS = YOLO_LAYOUT_CLASS_NAMES

# Canonical corner keys used for warp / quality (tl, tr, br, bl).
_LAYOUT_CORNER_ALIASES: dict[str, str] = {
    "corner_tl": "tl",
    "corner_tr": "tr",
    "corner_bl": "bl",
    "corner_br": "br",
    "top_left": "tl",
    "top_right": "tr",
    "bottom_left": "bl",
    "bottom_right": "br",
}
_LAYOUT_CORNER_ORDER = ("tl", "tr", "br", "bl")


def normalize_layout_field_label(label: str) -> str:
    key = label.strip().lower()
    return LAYOUT_FIELD_ALIASES.get(key, key)


def is_layout_skip_label(label: str) -> bool:
    key = label.strip().lower()
    if is_layout_corner_label(key):
        return True
    if key.startswith("corner_"):
        return True
    if key.endswith("_cccd"):
        return True
    return key in LAYOUT_SKIP_LABELS


def is_layout_portrait_label(label: str) -> bool:
    canonical = normalize_layout_field_label(label)
    return canonical in PORTRAIT_LAYOUT_LABELS


def is_layout_ocr_field_label(label: str) -> bool:
    if is_layout_skip_label(label) or is_layout_portrait_label(label):
        return False
    return normalize_layout_field_label(label) in LAYOUT_TEXT_FIELD_LABELS


def normalize_layout_corner_key(label: str) -> str | None:
    return _LAYOUT_CORNER_ALIASES.get(label.strip().lower())


def is_layout_corner_label(label: str) -> bool:
    return normalize_layout_corner_key(label) is not None


def extract_layout_corners(fields: list[LayoutField]) -> np.ndarray | None:
    """Return 4 corner points [tl, tr, br, bl] when YOLO detects all corners."""
    best: dict[str, LayoutField] = {}
    for item in fields:
        key = normalize_layout_corner_key(item.label)
        if key is None:
            continue
        current = best.get(key)
        if current is None or item.confidence > current.confidence:
            best[key] = item

    if not all(key in best for key in _LAYOUT_CORNER_ORDER):
        return None

    points: list[list[float]] = []
    for key in _LAYOUT_CORNER_ORDER:
        x1, y1, x2, y2 = best[key].bbox
        points.append([(x1 + x2) / 2.0, (y1 + y2) / 2.0])
    return np.array(points, dtype=np.float32)


def has_all_layout_corners(fields: list[LayoutField]) -> bool:
    return extract_layout_corners(fields) is not None


class YOLOLayoutDetector:
    def __init__(self, config: PipelineConfig | None = None) -> None:
        self.config = config or PipelineConfig()
        self._model = None

    def diagnostics(self) -> dict[str, object]:
        model_path = self.config.yolo_layout_model
        return {
            "model_path": str(model_path) if model_path else None,
            "ready": bool(model_path and model_path.is_file()),
            "labels": list(YOLO_LAYOUT_CLASS_NAMES),
            "field_aliases": LAYOUT_FIELD_ALIASES,
        }

    def _lazy_init(self) -> bool:
        if self._model is not None:
            return True
        model_path = self.config.yolo_layout_model
        if model_path is None or not model_path.is_file():
            return False
        try:
            from ultralytics import YOLO
        except ImportError:
            return False
        self._model = YOLO(str(model_path))
        return True

    def detect(self, image: np.ndarray) -> list[LayoutField]:
        if not self._lazy_init():
            height, width = image.shape[:2]
            return [
                LayoutField(
                    label="full_page",
                    bbox=(0, 0, width, height),
                    confidence=1.0,
                )
            ]

        assert self._model is not None
        results = self._model.predict(
            source=image,
            conf=self.config.yolo_layout_confidence,
            verbose=False,
        )
        if not results:
            return []

        result = results[0]
        names = result.names or {}
        fields: list[LayoutField] = []
        boxes = result.boxes
        if boxes is None:
            return fields

        xyxy = boxes.xyxy.cpu().numpy()
        confidences = boxes.conf.cpu().numpy()
        classes = boxes.cls.cpu().numpy().astype(int)

        for box, confidence, class_id in zip(xyxy, confidences, classes, strict=False):
            label = str(names.get(int(class_id), class_id))
            x1, y1, x2, y2 = [int(value) for value in box]
            fields.append(
                LayoutField(
                    label=label,
                    bbox=(max(0, x1), max(0, y1), max(x1 + 1, x2), max(y1 + 1, y2)),
                    confidence=float(confidence),
                )
            )
        return fields or [
            LayoutField(
                label="full_page",
                bbox=(0, 0, image.shape[1], image.shape[0]),
                confidence=1.0,
            )
        ]
