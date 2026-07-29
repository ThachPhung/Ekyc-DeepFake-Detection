"""End-to-end document analysis pipeline."""

from __future__ import annotations

import json
import time
from pathlib import Path

import cv2
import numpy as np

from ekyc_document.config import PipelineConfig
from ekyc_document.field_polish import (
    apply_mrz_name_correction,
    correct_id_number_from_mrz,
    polish_extracted_fields,
)
from ekyc_document.layout_field_parse import apply_document_status_checks
from ekyc_document.face_extraction import FaceExtractor
from ekyc_document.image_orientation import OrientResult, auto_orient_document, load_bgr_with_exif
from ekyc_document.llm_extract import LLMFieldExtractor
from ekyc_document.ocr import OCREngine, OCRResult
from ekyc_document.parser import detect_document_type, merge_two_sides, parse_document
from ekyc_document.private_store import PrivateRecordStore
from ekyc_document.quality_check import assess_image_quality
from ekyc_document.schemas import DocumentAnalysisResult, DocumentType, FaceResult, LLMUsageSummary, ParsedFields


class DocumentPipeline:
    """
    Image stage (OCR + face): ảnh → raw OCR text + ảnh chân dung.
    Text stage (LLM): OCR + rule merge → LLM extract → LLM review tổng thể.
    """

    def __init__(self, config: PipelineConfig | None = None) -> None:
        self.config = config or PipelineConfig()
        self._ocr: OCREngine | None = None
        self._face: FaceExtractor | None = None
        self._private_store: PrivateRecordStore | None = None
        self._llm: LLMFieldExtractor | None = None

    @property
    def ocr(self) -> OCREngine:
        if self._ocr is None:
            self._ocr = OCREngine(self.config)
        return self._ocr

    @property
    def face(self) -> FaceExtractor:
        if self._face is None:
            self._face = FaceExtractor(self.config)
        return self._face

    @property
    def private_store(self) -> PrivateRecordStore:
        if self._private_store is None:
            self._private_store = PrivateRecordStore(self.config)
        return self._private_store

    @property
    def llm(self) -> LLMFieldExtractor:
        if self._llm is None:
            self._llm = LLMFieldExtractor(self.config)
        return self._llm

    def load_image(self, source: str | Path | bytes | np.ndarray) -> np.ndarray:
        if isinstance(source, np.ndarray):
            return source
        if isinstance(source, (str, Path)):
            return load_bgr_with_exif(source)
        if isinstance(source, bytes):
            arr = np.frombuffer(source, dtype=np.uint8)
            image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if image is None:
                raise ValueError("Cannot decode image bytes")
            return image
        raise TypeError(f"Unsupported image source: {type(source)!r}")

    def _prepare_document_image(
        self, bgr: np.ndarray
    ) -> tuple[np.ndarray, OrientResult, np.ndarray]:
        if not self.config.auto_orient_document:
            oriented = OrientResult(image=bgr, rotation_degrees=0, auto_rotated=False)
        else:
            oriented = auto_orient_document(
                bgr,
                self.ocr,
                portrait_ratio=self.config.auto_orient_portrait_ratio,
                probe_max_side=self.config.auto_orient_probe_max_side,
            )

        pre_warp = oriented.image
        image = self._apply_document_warp(oriented.image)
        if image is not oriented.image:
            oriented = OrientResult(
                image=image,
                rotation_degrees=oriented.rotation_degrees,
                auto_rotated=oriented.auto_rotated,
                warning=oriented.warning,
            )
        return image, oriented, pre_warp

    def _apply_document_warp(self, bgr: np.ndarray, warnings: list[str] | None = None) -> np.ndarray:
        if not self.config.document_warp_enabled:
            return bgr

        from ekyc_document.ocr_stack.document_warp import warp_document

        warp = warp_document(bgr, self.config)
        if warnings is not None and warp.warning:
            warnings.append(warp.warning)
        return warp.image if warp.applied else bgr

    def _field_ocr_engine(self) -> OCREngine:
        """RapidOCR on YOLO crops — không dùng vietocr_stack full-page."""
        from dataclasses import replace

        if self.config.ocr_engine in {"rapidocr_ppocrv5", "rapidocr_ppocrv6", "rapidocr"}:
            return self.ocr
        field_config = replace(self.config, ocr_engine=self.config.ocr_fallback_engine)
        return OCREngine(field_config)

    def _analyze_two_sides_yolo_layout(
        self,
        front_bgr: np.ndarray,
        back_bgr: np.ndarray,
        *,
        document_type_hint: DocumentType | None,
        include_face_crop: bool,
        save_private_record: bool,
        front_quality,
        back_quality,
        warnings: list[str],
        timings_ms: dict[str, float],
        total_started: float,
        skip_ocr_if_low_quality: bool,
    ) -> DocumentAnalysisResult:
        from ekyc_document.ocr_stack.layout_detect import YOLOLayoutDetector
        from ekyc_document.yolo_layout_pipeline import (
            apply_two_sides_field_policy,
            build_two_sides_llm_text,
            collect_back_id_search_text,
            extract_layout_side,
            layout_pipeline_ready,
            portrait_to_face_result,
            validate_cccd_two_sides_id,
        )

        if not layout_pipeline_ready(self.config):
            raise RuntimeError("YOLO layout pipeline chưa sẵn sàng.")

        if skip_ocr_if_low_quality and min(front_quality.score, back_quality.score) < self.config.min_quality_score:
            warnings.append("Bỏ qua OCR do chất lượng ảnh thấp.")
            return DocumentAnalysisResult(
                document_type=document_type_hint or "CCCD",
                ocr_confidence=0.0,
                image_quality_score=min(front_quality.score, back_quality.score),
                document_face_detected=False,
                warnings=warnings,
                success=False,
                quality_details=front_quality.details,
                timings_ms={"total": _elapsed_ms(total_started)},
            )

        detector = YOLOLayoutDetector(self.config)
        field_ocr = self._field_ocr_engine()

        front_started = time.perf_counter()
        front_layout = extract_layout_side(
            front_bgr, side="front", config=self.config, detector=detector, ocr=field_ocr
        )
        timings_ms["front_yolo_ocr"] = _elapsed_ms(front_started)

        back_started = time.perf_counter()
        back_layout = extract_layout_side(
            back_bgr, side="back", config=self.config, detector=detector, ocr=field_ocr
        )
        timings_ms["back_yolo_ocr"] = _elapsed_ms(back_started)

        if not front_layout.labeled_text and not back_layout.labeled_text:
            warnings.append("YOLO layout không OCR được field nào — fallback full-page OCR.")
            raise RuntimeError("empty yolo layout ocr")

        raw_ocr_text = build_two_sides_llm_text(front_layout, back_layout)
        ocr_confidence = _average_nonzero(front_layout.ocr_confidence, back_layout.ocr_confidence)
        back_full_ocr: OCRResult | None = None

        def get_back_full_ocr() -> OCRResult:
            nonlocal back_full_ocr
            if back_full_ocr is None:
                back_full_started = time.perf_counter()
                back_full_ocr = field_ocr.run(back_bgr)
                timings_ms["back_full_ocr"] = _elapsed_ms(back_full_started)
            return back_full_ocr

        document_type, parsed_fields, llm_usage = self._extract_fields_from_two_sides(
            front_layout.labeled_text,
            back_layout.labeled_text,
            document_type_hint=document_type_hint or "CCCD",
            ocr_confidence=ocr_confidence,
            apply_llm=True,
            warnings=warnings,
            timings_ms=timings_ms,
        )

        if document_type == "CCCD" and parsed_fields is not None:
            back_id_text = collect_back_id_search_text(back_layout)
            sides_ok, side_warnings = validate_cccd_two_sides_id(
                parsed_fields.id_number,
                back_id_text,
            )
            if not sides_ok:
                full_back = get_back_full_ocr()
                parsed_fields = correct_id_number_from_mrz(parsed_fields, full_back.raw_text)
                back_id_text = f"{back_id_text}\n{full_back.raw_text}".strip()
                sides_ok, side_warnings = validate_cccd_two_sides_id(
                    parsed_fields.id_number,
                    back_id_text,
                )
                if sides_ok:
                    warnings.append(
                        "Đối chiếu ID mặt sau khớp qua OCR full-page (MRZ/id_back dài)."
                    )
            warnings.extend(side_warnings)
            if not sides_ok:
                warnings.append(
                    "Đối chiếu mặt trước/mặt sau không đạt — cần kiểm tra lại ảnh."
                )
                parsed_fields = apply_two_sides_field_policy(
                    parsed_fields,
                    front_labeled_text=front_layout.labeled_text,
                    sides_ok=False,
                    document_type=document_type,
                )
            if not parsed_fields.issue_date or not parsed_fields.issue_place:
                full_back = get_back_full_ocr()
                parsed_fields = _merge_missing_back_side_fields(
                    parsed_fields,
                    full_back.raw_text,
                    document_type=document_type,
                )
            if not parsed_fields.issue_date:
                warnings.append("Không trích xuất được ngày cấp CCCD từ mặt sau.")
            if not parsed_fields.issue_place:
                warnings.append("Không trích xuất được nơi cấp CCCD từ mặt sau.")

        face = portrait_to_face_result(
            front_layout.portrait_crop,
            front_layout.portrait_bbox,
            include_crop=include_face_crop,
        )
        if not face.detected and self.config.use_yolo_layout_pipeline:
            warnings.append("Fallback InsightFace trên ảnh mặt trước full.")
            face_started = time.perf_counter()
            face = self.face.extract(front_bgr, include_crop=include_face_crop)
            timings_ms["face_extract_fallback"] = _elapsed_ms(face_started)

        record_id: str | None = None
        image_quality_score = min(front_quality.score, back_quality.score)
        if save_private_record:
            record_id = self.private_store.save_front_record(
                document_type=document_type,
                parsed_fields=parsed_fields,
                ocr_confidence=ocr_confidence,
                image_quality_score=image_quality_score,
                side="both",
            )

        timings_ms["total"] = _elapsed_ms(total_started)
        warnings.insert(0, f"Pipeline: YOLO layout ({self.config.yolo_layout_model.name})")

        return DocumentAnalysisResult(
            document_type=document_type,
            ocr_confidence=round(ocr_confidence, 4),
            image_quality_score=image_quality_score,
            document_face_detected=face.detected,
            document_face_confident=face.confident,
            document_face_confidence=face.quality_score,
            warnings=warnings,
            record_id=record_id,
            success=True,
            quality_details=front_quality.details,
            parsed_fields=parsed_fields,
            face=face,
            ocr_lines=[*front_layout.ocr_lines, *back_layout.ocr_lines],
            raw_ocr_text=raw_ocr_text,
            timings_ms=timings_ms,
            llm_usage=llm_usage,
        )

    def _run_ocr_on_image(
        self,
        bgr: np.ndarray,
        *,
        skip_if_low_quality: bool,
        quality_score: float,
        side_label: str,
        warnings: list[str],
        timings_ms: dict[str, float],
        timing_key: str = "ocr",
    ) -> OCRResult:
        if skip_if_low_quality and quality_score < self.config.min_quality_score:
            prefix = f"{side_label}: " if side_label else ""
            warnings.append(f"{prefix}Bỏ qua OCR do chất lượng ảnh thấp.")
            return OCRResult(lines=[], confidence=0.0, raw_text="", engine=str(self.config.ocr_engine))

        started = time.perf_counter()
        ocr_result = self.ocr.run(bgr)
        timings_ms[timing_key] = _elapsed_ms(started)
        if ocr_result.confidence < 0.5:
            prefix = f"{side_label}: " if side_label else ""
            warnings.append(f"{prefix}Độ tin cậy OCR thấp — nên chụp lại ảnh rõ hơn.")
        return ocr_result

    def _apply_llm_and_polish(
        self,
        *,
        document_type: DocumentType,
        document_side: str,
        rule_fields: ParsedFields | None,
        raw_ocr_text: str,
        ocr_confidence: float,
        apply_llm: bool,
        warnings: list[str],
        timings_ms: dict[str, float],
        parse_warnings: list[str],
    ) -> tuple[ParsedFields | None, LLMUsageSummary | None]:
        if apply_llm and self.llm.should_run():
            result = self.llm.extract(
                raw_ocr_text,
                document_type=document_type,
                rule_fields=rule_fields,
                ocr_confidence=ocr_confidence,
                fallback_fields=rule_fields,
                timings_ms=timings_ms,
            )

            if result.used and result.fields is not None:
                if result.reviewed:
                    warnings.append(
                        f"LLM đã review tổng thể sau merge OCR "
                        f"({result.provider}/{result.model})."
                    )
                else:
                    warnings.append(
                        f"Trích xuất text bằng LLM ({result.provider}/{result.model})."
                    )
                if result.usage is not None and result.usage.total_tokens > 0:
                    warnings.append(
                        "LLM tokens: "
                        f"prompt={result.usage.total_prompt_tokens}, "
                        f"completion={result.usage.total_completion_tokens}, "
                        f"total={result.usage.total_tokens}."
                    )
                warnings.extend(
                    _field_extraction_warnings(document_type, result.fields, document_side)
                )
                polished = polish_extracted_fields(result.fields)
                return apply_document_status_checks(polished, warnings), result.usage

            if result.error:
                warnings.append(f"LLM extract thất bại, fallback rule parser: {result.error}")
                warnings.extend(parse_warnings)
                polished = polish_extracted_fields(rule_fields)
                return apply_document_status_checks(polished, warnings), result.usage
        elif apply_llm and self.config.llm_extract_enabled:
            warnings.append("LLM chưa sẵn sàng — dùng rule parser cho text.")
            timings_ms.setdefault("llm_extract", 0.0)
            timings_ms.setdefault("llm_review", 0.0)
            warnings.extend(parse_warnings)
        else:
            timings_ms.setdefault("llm_extract", 0.0)
            timings_ms.setdefault("llm_review", 0.0)
            warnings.extend(parse_warnings)

        polished = polish_extracted_fields(rule_fields)
        return apply_document_status_checks(polished, warnings), None

    def _extract_fields_from_text(
        self,
        raw_ocr_text: str,
        *,
        document_type_hint: DocumentType | None,
        document_side: str,
        ocr_confidence: float,
        apply_llm: bool,
        warnings: list[str],
        timings_ms: dict[str, float],
    ) -> tuple[DocumentType, ParsedFields | None, LLMUsageSummary | None]:
        parse_started = time.perf_counter()
        parse = parse_document(
            raw_ocr_text,
            forced_type=document_type_hint,
            side=document_side if document_side in {"front", "back"} else "front",
        )
        timings_ms["parse"] = _elapsed_ms(parse_started)
        document_type = document_type_hint or parse.document_type
        fields, llm_usage = self._apply_llm_and_polish(
            document_type=document_type,
            document_side=document_side,
            rule_fields=parse.fields,
            raw_ocr_text=raw_ocr_text,
            ocr_confidence=ocr_confidence,
            apply_llm=apply_llm,
            warnings=warnings,
            timings_ms=timings_ms,
            parse_warnings=parse.warnings,
        )
        return document_type, fields, llm_usage

    def _extract_fields_from_two_sides(
        self,
        front_raw_text: str,
        back_raw_text: str,
        *,
        document_type_hint: DocumentType | None,
        ocr_confidence: float,
        apply_llm: bool,
        warnings: list[str],
        timings_ms: dict[str, float],
    ) -> tuple[DocumentType, ParsedFields | None, LLMUsageSummary | None]:
        parse_started = time.perf_counter()
        merged = merge_two_sides(
            front_raw_text,
            back_raw_text,
            forced_type=document_type_hint,
        )
        timings_ms["parse"] = _elapsed_ms(parse_started)
        document_type = document_type_hint or merged.document_type
        warnings.extend(merged.warnings)

        combined_raw_text = "\n\n".join(
            part
            for part in (
                f"[MAT_TRUOC]\n{front_raw_text.strip()}",
                f"[MAT_SAU]\n{back_raw_text.strip()}",
            )
            if part.strip()
        )
        fields, llm_usage = self._apply_llm_and_polish(
            document_type=document_type,
            document_side="both",
            rule_fields=merged.fields,
            raw_ocr_text=combined_raw_text,
            ocr_confidence=ocr_confidence,
            apply_llm=apply_llm,
            warnings=warnings,
            timings_ms=timings_ms,
            parse_warnings=[],
        )
        if document_type == "CCCD" and fields is not None:
            fields = apply_mrz_name_correction(fields, combined_raw_text)
            fields = correct_id_number_from_mrz(fields, combined_raw_text)
            fields = polish_extracted_fields(fields)
            fields = apply_document_status_checks(fields, warnings)
        return document_type, fields, llm_usage

    def analyze(
        self,
        image: str | Path | bytes | np.ndarray,
        *,
        document_type_hint: DocumentType | None = None,
        include_face_crop: bool = False,
        skip_ocr_if_low_quality: bool = False,
        save_private_record: bool = True,
        expect_document_face: bool = True,
        document_side: str = "front",
        apply_llm: bool = True,
    ) -> DocumentAnalysisResult:
        total_started = time.perf_counter()
        bgr = self.load_image(image)
        warnings: list[str] = []

        orient_started = time.perf_counter()
        bgr, orient, pre_warp = self._prepare_document_image(bgr)
        timings_ms = {"orient": _elapsed_ms(orient_started)}
        if orient.warning:
            warnings.append(orient.warning)

        quality_started = time.perf_counter()
        quality = assess_image_quality(bgr, self.config, corner_probe_image=pre_warp)
        timings_ms["quality"] = _elapsed_ms(quality_started)
        warnings.extend(quality.warnings)

        ocr_result = self._run_ocr_on_image(
            bgr,
            skip_if_low_quality=skip_ocr_if_low_quality,
            quality_score=quality.score,
            side_label="",
            warnings=warnings,
            timings_ms=timings_ms,
        )
        if ocr_result.warnings:
            warnings.extend(ocr_result.warnings)

        document_type, parsed_fields, llm_usage = self._extract_fields_from_text(
            ocr_result.raw_text,
            document_type_hint=document_type_hint,
            document_side=document_side,
            ocr_confidence=ocr_result.confidence,
            apply_llm=apply_llm,
            warnings=warnings,
            timings_ms=timings_ms,
        )

        if expect_document_face:
            face_started = time.perf_counter()
            face = self.face.extract(bgr, include_crop=include_face_crop)
            timings_ms["face_extract"] = _elapsed_ms(face_started)
            if not face.detected:
                warnings.append("Không phát hiện ảnh chân dung trên giấy tờ.")
            elif not face.confident:
                warnings.extend(face.warnings)
        else:
            face = FaceResult(detected=False)
            timings_ms["face_extract"] = 0.0

        record_id: str | None = None
        if save_private_record:
            record_id = self.private_store.save_front_record(
                document_type=document_type,
                parsed_fields=parsed_fields,
                ocr_confidence=ocr_result.confidence,
                image_quality_score=quality.score,
            )

        timings_ms["total"] = _elapsed_ms(total_started)
        return DocumentAnalysisResult(
            document_type=document_type,
            ocr_confidence=round(ocr_result.confidence, 4),
            image_quality_score=quality.score,
            document_face_detected=face.detected,
            document_face_confident=face.confident,
            document_face_confidence=face.quality_score,
            warnings=warnings,
            record_id=record_id,
            success=True,
            quality_details=quality.details,
            parsed_fields=parsed_fields,
            face=face,
            ocr_lines=ocr_result.lines,
            raw_ocr_text=ocr_result.raw_text,
            timings_ms=timings_ms,
            llm_usage=llm_usage,
        )

    def analyze_two_sides(
        self,
        front_image: str | Path | bytes | np.ndarray,
        back_image: str | Path | bytes | np.ndarray | None = None,
        *,
        document_type_hint: DocumentType | None = None,
        include_face_crop: bool = False,
        skip_ocr_if_low_quality: bool = False,
        save_private_record: bool = True,
        expect_document_face: bool = True,
    ) -> DocumentAnalysisResult:
        if back_image is None:
            return self.analyze(
                front_image,
                document_type_hint=document_type_hint,
                include_face_crop=include_face_crop,
                skip_ocr_if_low_quality=skip_ocr_if_low_quality,
                save_private_record=save_private_record,
                expect_document_face=expect_document_face,
            )

        total_started = time.perf_counter()
        warnings: list[str] = []
        timings_ms: dict[str, float] = {}

        front_bgr = self.load_image(front_image)
        front_orient_started = time.perf_counter()
        front_bgr, front_orient, front_pre_warp = self._prepare_document_image(front_bgr)
        timings_ms["front_orient"] = _elapsed_ms(front_orient_started)
        if front_orient.warning:
            warnings.append(front_orient.warning)

        front_quality_started = time.perf_counter()
        front_quality = assess_image_quality(
            front_bgr, self.config, corner_probe_image=front_pre_warp
        )
        timings_ms["front_quality"] = _elapsed_ms(front_quality_started)
        warnings.extend(front_quality.warnings)

        back_bgr = self.load_image(back_image)
        back_orient_started = time.perf_counter()
        back_bgr, back_orient, back_pre_warp = self._prepare_document_image(back_bgr)
        timings_ms["back_orient"] = _elapsed_ms(back_orient_started)
        if back_orient.warning:
            warnings.append(f"Mặt sau: {back_orient.warning}")

        back_quality_started = time.perf_counter()
        back_quality = assess_image_quality(
            back_bgr, self.config, corner_probe_image=back_pre_warp
        )
        timings_ms["back_quality"] = _elapsed_ms(back_quality_started)
        warnings.extend(f"Mặt sau: {warning}" for warning in back_quality.warnings)

        from ekyc_document.yolo_layout_pipeline import layout_pipeline_ready

        if layout_pipeline_ready(self.config):
            try:
                return self._analyze_two_sides_yolo_layout(
                    front_bgr,
                    back_bgr,
                    document_type_hint=document_type_hint,
                    include_face_crop=include_face_crop,
                    save_private_record=save_private_record,
                    front_quality=front_quality,
                    back_quality=back_quality,
                    warnings=warnings,
                    timings_ms=timings_ms,
                    total_started=total_started,
                    skip_ocr_if_low_quality=skip_ocr_if_low_quality,
                )
            except RuntimeError as exc:
                warnings.append(f"YOLO layout fallback full-page OCR: {exc}")

        front_ocr = self._run_ocr_on_image(
            front_bgr,
            skip_if_low_quality=skip_ocr_if_low_quality,
            quality_score=front_quality.score,
            side_label="",
            warnings=warnings,
            timings_ms=timings_ms,
            timing_key="front_ocr",
        )
        if front_ocr.warnings:
            warnings.extend(front_ocr.warnings)

        if expect_document_face:
            face_started = time.perf_counter()
            face = self.face.extract(front_bgr, include_crop=include_face_crop)
            timings_ms["face_extract"] = _elapsed_ms(face_started)
            if not face.detected:
                warnings.append("Không phát hiện ảnh chân dung trên giấy tờ.")
            elif not face.confident:
                warnings.extend(face.warnings)
        else:
            face = FaceResult(detected=False)
            timings_ms["face_extract"] = 0.0

        back_ocr = self._run_ocr_on_image(
            back_bgr,
            skip_if_low_quality=skip_ocr_if_low_quality,
            quality_score=back_quality.score,
            side_label="Mặt sau",
            warnings=warnings,
            timings_ms=timings_ms,
            timing_key="back_ocr",
        )
        if back_ocr.warnings:
            warnings.extend(f"Mặt sau: {warning}" for warning in back_ocr.warnings)

        ocr_confidence = _average_nonzero(front_ocr.confidence, back_ocr.confidence)
        document_type, parsed_fields, llm_usage = self._extract_fields_from_two_sides(
            front_ocr.raw_text,
            back_ocr.raw_text,
            document_type_hint=document_type_hint
            or detect_document_type(front_ocr.raw_text),
            ocr_confidence=ocr_confidence,
            apply_llm=True,
            warnings=warnings,
            timings_ms=timings_ms,
        )

        if document_type == "CCCD" and parsed_fields is not None:
            if not parsed_fields.issue_date:
                warnings.append("Không trích xuất được ngày cấp CCCD từ mặt sau.")
            if not parsed_fields.issue_place:
                warnings.append("Không trích xuất được nơi cấp CCCD từ mặt sau.")

        record_id: str | None = None
        image_quality_score = min(front_quality.score, back_quality.score)
        if save_private_record:
            record_id = self.private_store.save_front_record(
                document_type=document_type,
                parsed_fields=parsed_fields,
                ocr_confidence=ocr_confidence,
                image_quality_score=image_quality_score,
                side="both",
            )

        timings_ms["total"] = _elapsed_ms(total_started)
        return DocumentAnalysisResult(
            document_type=document_type,
            ocr_confidence=round(ocr_confidence, 4),
            image_quality_score=image_quality_score,
            document_face_detected=face.detected,
            document_face_confident=face.confident,
            document_face_confidence=face.quality_score,
            warnings=warnings,
            record_id=record_id,
            success=True,
            quality_details=front_quality.details,
            parsed_fields=parsed_fields,
            face=face,
            ocr_lines=[*front_ocr.lines, *back_ocr.lines],
            raw_ocr_text="\n".join(
                part for part in (front_ocr.raw_text, back_ocr.raw_text) if part
            ),
            timings_ms=timings_ms,
            llm_usage=llm_usage,
        )


def _field_extraction_warnings(
    document_type: DocumentType,
    fields: ParsedFields,
    side: str,
) -> list[str]:
    if side == "back":
        return []

    warnings: list[str] = []
    if document_type == "CCCD" and not fields.id_number:
        warnings.append("Không trích xuất được số CCCD (12 chữ số).")
    if document_type == "GPLX" and not fields.id_number:
        warnings.append("Không trích xuất được số GPLX.")
    if document_type == "PASSPORT" and not fields.passport_number:
        warnings.append("Không trích xuất được số hộ chiếu.")
    if document_type == "CCCD" and side in {"front", "both"} and not fields.expiry_date:
        warnings.append("Không trích xuất được ngày hết hạn CCCD.")
    if document_type == "UNKNOWN":
        warnings.append("Không xác định được loại giấy tờ từ OCR.")
    return warnings


def _average_nonzero(*values: float) -> float:
    nonzero = [value for value in values if value > 0]
    if not nonzero:
        return 0.0
    return float(sum(nonzero) / len(nonzero))


def _elapsed_ms(started_at: float) -> float:
    return round((time.perf_counter() - started_at) * 1000.0, 2)


def analyze_document(
    image: str | Path | bytes | np.ndarray,
    **kwargs,
) -> DocumentAnalysisResult:
    return DocumentPipeline().analyze(image, **kwargs)


def _merge_missing_back_side_fields(
    fields: ParsedFields | None,
    back_raw_text: str,
    *,
    document_type: DocumentType,
) -> ParsedFields | None:
    if fields is None or document_type != "CCCD" or not back_raw_text.strip():
        return fields

    back_parse = parse_document(
        back_raw_text,
        forced_type=document_type,
        side="back",
    )
    back_fields = polish_extracted_fields(back_parse.fields)
    if back_fields is None:
        return fields

    data = fields.model_dump()
    for field_name in ("issue_date", "issue_place", "expiry_date"):
        if data.get(field_name):
            continue
        value = getattr(back_fields, field_name)
        if value:
            data[field_name] = value

    return ParsedFields(**data)


def main() -> None:
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="eKYC document analysis pipeline")
    parser.add_argument("front", help="Path to front document image")
    parser.add_argument("--back", help="Optional path to back document image")
    parser.add_argument(
        "--type",
        choices=["CCCD", "GPLX", "PASSPORT"],
        help="Optional document type hint",
    )
    parser.add_argument("--full", action="store_true", help="Output full JSON")
    parser.add_argument(
        "--fields-only",
        action="store_true",
        help="Print only parsed_fields (quê quán, thường trú, ...)",
    )
    parser.add_argument("--face-crop", action="store_true", help="Include base64 face crop")
    parser.add_argument(
        "--no-face",
        action="store_true",
        help="Skip face extraction (OCR-only, no insightface required)",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Do not write PII to private storage",
    )
    args = parser.parse_args()

    pipeline = DocumentPipeline()
    if args.back:
        result = pipeline.analyze_two_sides(
            args.front,
            args.back,
            document_type_hint=args.type,
            include_face_crop=args.face_crop,
            save_private_record=not args.no_save,
            expect_document_face=not args.no_face,
        )
    else:
        result = pipeline.analyze(
            args.front,
            document_type_hint=args.type,
            include_face_crop=args.face_crop,
            save_private_record=not args.no_save,
            expect_document_face=not args.no_face,
        )

    if args.fields_only and result.parsed_fields is not None:
        payload = result.parsed_fields.model_dump()
    elif args.full:
        payload = result.to_full_json()
    else:
        payload = result.to_backend_json()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if result.record_id:
        private_path = (
            pipeline.config.private_storage_dir / "records" / f"{result.record_id}.json"
        )
        print(f"\n[private] PII saved → {private_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
