"""End-to-end OCR stack: YOLO layout warp → field layout → DBNet lines → VietOCR."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ekyc_document.config import PipelineConfig
from ekyc_document.document_preprocess import preprocess_for_ocr
from ekyc_document.ocr import _sort_lines_by_position
from ekyc_document.ocr_stack.dbnet_detect import DBNetDetector, crop_line_image
from ekyc_document.ocr_stack.document_warp import WarpResult, warp_document
from ekyc_document.ocr_stack.layout_detect import LayoutField, YOLOLayoutDetector
from ekyc_document.ocr_stack.vietocr_recognizer import VietOCRRecognizer
from ekyc_document.schemas import OCRLine


@dataclass
class VietOCRStackResult:
    lines: list[OCRLine]
    confidence: float
    raw_text: str
    engine: str
    warp: WarpResult | None = None
    layout_fields: list[LayoutField] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    stages: dict[str, object] = field(default_factory=dict)


class VietOCRStackPipeline:
    """
    Production-oriented OCR pipeline:
    1. YOLO layout corner boxes + perspective transform
    2. YOLO layout field boxes
    3. DBNet text-line polygons inside each field
    4. VietOCR recognition per line crop
    """

    def __init__(self, config: PipelineConfig | None = None) -> None:
        self.config = config or PipelineConfig()
        self._layout = YOLOLayoutDetector(self.config)
        self._dbnet = DBNetDetector(self.config)
        self._recognizer = VietOCRRecognizer(self.config)

    def diagnostics(self) -> dict[str, object]:
        return {
            "engine": "vietocr_stack",
            "warp_enabled": self.config.document_warp_enabled,
            "layout": self._layout.diagnostics(),
            "dbnet": self._dbnet.diagnostics(),
            "vietocr": self._recognizer.diagnostics(),
        }

    def run(self, image: np.ndarray) -> VietOCRStackResult:
        warnings: list[str] = []
        stages: dict[str, object] = {}

        working = preprocess_for_ocr(image) if self.config.ocr_preprocess else image
        warp = warp_document(working, self.config)
        stages["warp_method"] = warp.method
        if warp.warning:
            warnings.append(warp.warning)
        if warp.applied:
            working = warp.image

        layout_fields = self._layout.detect(working)
        stages["layout_field_count"] = len(layout_fields)

        line_boxes: list[tuple[list[list[float]], str]] = []
        for layout_field in layout_fields:
            x1, y1, x2, y2 = layout_field.bbox
            boxes = self._dbnet.detect(working, roi=(x1, y1, x2, y2))
            for box in boxes:
                line_boxes.append((box.polygon, layout_field.label))

        if not line_boxes:
            boxes = self._dbnet.detect(working)
            line_boxes = [(box.polygon, "full_page") for box in boxes]

        stages["line_box_count"] = len(line_boxes)

        if not self._recognizer.is_ready():
            warnings.append(
                "VietOCR chưa sẵn sàng — cài vietocr và weights, hoặc fallback RapidOCR."
            )
            return VietOCRStackResult(
                lines=[],
                confidence=0.0,
                raw_text="",
                engine="vietocr_stack",
                warp=warp,
                layout_fields=layout_fields,
                warnings=warnings,
                stages=stages,
            )

        ocr_lines: list[OCRLine] = []
        confidences: list[float] = []
        for polygon, _label in line_boxes:
            crop = crop_line_image(working, polygon)
            text, confidence = self._recognizer.recognize(crop)
            cleaned = text.strip()
            if not cleaned:
                continue
            ocr_lines.append(
                OCRLine(
                    text=cleaned,
                    confidence=float(confidence),
                    bbox=polygon,
                )
            )
            confidences.append(float(confidence))

        ocr_lines = _sort_lines_by_position(ocr_lines)
        raw_text = "\n".join(line.text for line in ocr_lines)
        avg_conf = float(np.mean(confidences)) if confidences else 0.0

        return VietOCRStackResult(
            lines=ocr_lines,
            confidence=avg_conf,
            raw_text=raw_text,
            engine="vietocr_stack",
            warp=warp,
            layout_fields=layout_fields,
            warnings=warnings,
            stages=stages,
        )
