"""OCR integration — VietOCR stack or RapidOCR (PP-OCRv5/v6)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ekyc_document.config import PipelineConfig
from ekyc_document.document_preprocess import preprocess_for_ocr
from ekyc_document.schemas import OCRLine

_SUPPORTED_ENGINES = frozenset(
    {"rapidocr_ppocrv5", "rapidocr_ppocrv6", "rapidocr", "vietocr_stack"}
)


@dataclass
class OCRResult:
    lines: list[OCRLine]
    confidence: float
    raw_text: str
    engine: str
    warnings: list[str] | None = None
    stages: dict[str, object] | None = None


class OCREngine:
    def __init__(self, config: PipelineConfig | None = None) -> None:
        self.config = config or PipelineConfig()
        self._reader = None
        self._vietocr_stack = None
        self._fallback_engine: OCREngine | None = None
        self._engine_name = self.config.ocr_engine

    def diagnostics(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "engine": self._engine_name,
            "preprocess": self.config.ocr_preprocess,
            "languages": self.config.ocr_languages,
        }
        if self._engine_name == "vietocr_stack":
            from ekyc_document.ocr_stack.pipeline import VietOCRStackPipeline

            payload["vietocr_stack"] = VietOCRStackPipeline(self.config).diagnostics()
        return payload

    def _lazy_init(self) -> None:
        if self._reader is not None or self._vietocr_stack is not None:
            return

        engine = self.config.ocr_engine
        if engine == "vietocr_stack":
            from ekyc_document.ocr_stack.pipeline import VietOCRStackPipeline

            self._vietocr_stack = VietOCRStackPipeline(self.config)
            self._engine_name = "vietocr_stack"
            return

        if engine in {"rapidocr_ppocrv5", "rapidocr_ppocrv6", "rapidocr"}:
            from rapidocr import RapidOCR
            from rapidocr.utils.typings import ModelType, OCRVersion

            lang = self.config.rapidocr_lang
            rec_model = self.config.rapidocr_rec_model.lower()
            params: dict[str, object] = {
                "Det.ocr_version": OCRVersion.PPOCRV6,
                "Det.lang_type": lang,
                "EngineConfig.onnxruntime.use_cuda": self.config.use_gpu,
            }
            if rec_model in {"latin_pp-ocrv5_rec_mobile", "latin"}:
                from rapidocr.utils.typings import LangRec

                params.update(
                    {
                        "Rec.ocr_version": OCRVersion.PPOCRV5,
                        "Rec.lang_type": LangRec.LATIN,
                        "Rec.model_type": ModelType.MOBILE,
                    }
                )
                self._engine_name = "rapidocr_ppocrv5"
            else:
                params.update(
                    {
                        "Rec.ocr_version": OCRVersion.PPOCRV6,
                        "Rec.lang_type": lang,
                        "Rec.model_type": ModelType.SMALL,
                    }
                )
                self._engine_name = "rapidocr_ppocrv6"
            self._reader = RapidOCR(params=params)
            return

        raise ValueError(
            f"OCR engine không hỗ trợ: {engine!r}. "
            f"Dùng một trong: {', '.join(sorted(_SUPPORTED_ENGINES))}."
        )

    def run(self, image: np.ndarray) -> OCRResult:
        self._lazy_init()

        if self._vietocr_stack is not None:
            stack_result = self._vietocr_stack.run(image)
            if stack_result.lines or not self.config.allow_heuristic_fallback:
                return OCRResult(
                    lines=stack_result.lines,
                    confidence=stack_result.confidence,
                    raw_text=stack_result.raw_text,
                    engine=stack_result.engine,
                    warnings=stack_result.warnings,
                    stages=stack_result.stages,
                )
            fallback = self._get_fallback_engine()
            fallback_result = fallback.run(image)
            warnings = list(stack_result.warnings or [])
            warnings.append(
                f"VietOCR stack trả rỗng — fallback sang {fallback_result.engine}."
            )
            return OCRResult(
                lines=fallback_result.lines,
                confidence=fallback_result.confidence,
                raw_text=fallback_result.raw_text,
                engine=f"{stack_result.engine}->{fallback_result.engine}",
                warnings=warnings,
                stages=stack_result.stages,
            )

        assert self._reader is not None

        prepared = preprocess_for_ocr(image) if self.config.ocr_preprocess else image
        if self._engine_name in {"rapidocr_ppocrv5", "rapidocr_ppocrv6"}:
            return self._run_rapidocr(prepared)
        raise RuntimeError(f"OCR reader chưa được khởi tạo cho engine {self._engine_name!r}.")

    def _get_fallback_engine(self) -> OCREngine:
        if self._fallback_engine is None:
            from dataclasses import replace

            fallback_config = replace(
                self.config,
                ocr_engine=self.config.ocr_fallback_engine,
                document_warp_enabled=False,
            )
            self._fallback_engine = OCREngine(fallback_config)
        return self._fallback_engine

    def _run_rapidocr(self, image: np.ndarray) -> OCRResult:
        result = self._reader(image)
        lines: list[OCRLine] = []
        confidences: list[float] = []
        if result is None or not getattr(result, "txts", None):
            return OCRResult(lines=[], confidence=0.0, raw_text="", engine=self._engine_name)

        boxes = getattr(result, "boxes", None)
        texts = getattr(result, "txts", None)
        scores = getattr(result, "scores", None)
        if boxes is None or texts is None or scores is None:
            return OCRResult(lines=[], confidence=0.0, raw_text="", engine=self._engine_name)

        for bbox, text, score in zip(boxes, texts, scores, strict=False):
            cleaned = str(text).strip()
            if not cleaned:
                continue
            polygon = [[float(x), float(y)] for x, y in bbox]
            lines.append(
                OCRLine(
                    text=cleaned,
                    confidence=float(score),
                    bbox=polygon,
                )
            )
            confidences.append(float(score))

        lines = _sort_lines_by_position(lines)
        raw_text = "\n".join(line.text for line in lines)
        avg_conf = float(np.mean(confidences)) if confidences else 0.0
        return OCRResult(
            lines=lines,
            confidence=avg_conf,
            raw_text=raw_text,
            engine=self._engine_name,
        )


def _sort_lines_by_position(lines: list[OCRLine]) -> list[OCRLine]:
    positioned = []
    for index, line in enumerate(lines):
        if not line.bbox:
            positioned.append((index, 0.0, 0.0, 0.0, line))
            continue
        xs = [point[0] for point in line.bbox]
        ys = [point[1] for point in line.bbox]
        positioned.append(
            (
                index,
                float(min(xs)),
                float((min(ys) + max(ys)) / 2),
                float(max(ys) - min(ys)),
                line,
            )
        )

    heights = [height for _, _, _, height, _ in positioned if height > 0]
    row_tolerance = max(18.0, (float(np.median(heights)) if heights else 30.0) * 0.8)
    rows: list[list[tuple[int, float, float, float, OCRLine]]] = []
    row_centers: list[float] = []

    for item in sorted(positioned, key=lambda value: (value[2], value[1], value[0])):
        _, _, center_y, _, _ = item
        for row_index, row_center in enumerate(row_centers):
            if abs(center_y - row_center) <= row_tolerance:
                rows[row_index].append(item)
                row_centers[row_index] = sum(row_item[2] for row_item in rows[row_index]) / len(
                    rows[row_index]
                )
                break
        else:
            rows.append([item])
            row_centers.append(center_y)

    sorted_lines: list[OCRLine] = []
    for row in rows:
        sorted_lines.extend(item[-1] for item in sorted(row, key=lambda value: (value[1], value[0])))
    return sorted_lines
