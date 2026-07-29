"""Document image quality assessment."""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from ekyc_document.config import PipelineConfig
from ekyc_document.schemas import QualityDetail


@dataclass
class QualityCheckResult:
    score: float
    details: QualityDetail
    warnings: list[str]


def _clip01(value: float) -> float:
    return float(max(0.0, min(1.0, value)))


def _blur_score(gray: np.ndarray) -> tuple[float, str | None]:
    variance = cv2.Laplacian(gray, cv2.CV_64F).var()
    # Typical sharp document photos: 100–800+
    score = _clip01((variance - 50.0) / 450.0)
    warning = None
    if score < 0.45:
        warning = "Ảnh bị mờ (blur). Vui lòng chụp lại rõ nét hơn."
    return score, warning


def _brightness_score(gray: np.ndarray) -> tuple[float, str | None]:
    mean = float(np.mean(gray))
    # Ideal range roughly 90–170 on 0–255 scale
    if 90.0 <= mean <= 170.0:
        score = 1.0
    elif mean < 90.0:
        score = _clip01(mean / 90.0)
    else:
        score = _clip01((255.0 - mean) / (255.0 - 170.0))
    warning = None
    if mean < 70.0:
        warning = "Ảnh quá tối. Cần thêm ánh sáng khi chụp."
    elif mean > 200.0:
        warning = "Ảnh quá sáng / overexposed."
    return score, warning


def _contrast_score(gray: np.ndarray) -> tuple[float, str | None]:
    std = float(np.std(gray))
    score = _clip01((std - 20.0) / 50.0)
    warning = None
    if score < 0.45:
        warning = "Độ tương phản thấp, chữ khó đọc."
    return score, warning


def _glare_score(gray: np.ndarray) -> tuple[float, str | None]:
    bright = gray > 245
    bright_ratio = float(np.count_nonzero(bright)) / gray.size
    # Penalize large saturated highlights
    score = _clip01(1.0 - (bright_ratio / 0.08))
    warning = None
    if bright_ratio > 0.05:
        warning = "Phát hiện vùng chói sáng (glare) trên giấy tờ."
    return score, warning


def _screenshot_score(gray: np.ndarray) -> tuple[float, str | None]:
    """Detect overly clean digital captures such as screenshots or scans."""
    if gray.size == 0:
        return 1.0, None

    h, w = gray.shape[:2]
    scale = min(1.0, 512.0 / max(h, w))
    if scale < 1.0:
        gray = cv2.resize(gray, (int(w * scale), int(h * scale)))

    smoothed = cv2.GaussianBlur(gray, (3, 3), 0)
    residual = float(np.mean(np.abs(gray.astype(np.float32) - smoothed.astype(np.float32)))) / 255.0
    lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    edges = cv2.Canny(gray, 80, 180)
    edge_ratio = float(np.count_nonzero(edges)) / edges.size
    mean = cv2.blur(gray.astype(np.float32), (9, 9))
    mean_sq = cv2.blur(gray.astype(np.float32) ** 2, (9, 9))
    local_std = np.sqrt(np.maximum(mean_sq - mean**2, 0.0))
    flat_ratio = float(np.count_nonzero(local_std < 2.0)) / local_std.size

    low_noise = _clip01((0.006 - residual) / 0.006)
    sharp_edges = _clip01((lap_var - 650.0) / 1800.0)
    edge_density = _clip01((edge_ratio - 0.035) / 0.12)
    flat_digital_regions = _clip01((flat_ratio - 0.35) / 0.4)
    suspicion = max(
        low_noise * max(sharp_edges, edge_density),
        flat_digital_regions * sharp_edges,
    )
    score = _clip01(1.0 - suspicion)

    warning = None
    if score < 0.55:
        warning = "Ảnh có dấu hiệu chụp màn hình/scan kỹ thuật số, nên dùng ảnh chụp camera thật."
    return score, warning


def _corners_score_yolo_layout(
    image: np.ndarray, config: PipelineConfig
) -> tuple[float, str | None] | None:
    """When YOLO layout detects all 4 corners, skip contour-based corner warning."""
    if not config.use_yolo_layout_pipeline:
        return None
    model_path = config.yolo_layout_model
    if model_path is None or not model_path.is_file():
        return None

    from ekyc_document.ocr_stack.layout_detect import YOLOLayoutDetector, extract_layout_corners

    fields = YOLOLayoutDetector(config).detect(image)
    corners = extract_layout_corners(fields)
    if corners is None:
        return None

    h, w = image.shape[:2]
    margin = min(h, w) * 0.03
    xs = corners[:, 0]
    ys = corners[:, 1]
    touches_border = (
        np.any(xs < margin)
        or np.any(xs > w - margin)
        or np.any(ys < margin)
        or np.any(ys > h - margin)
    )
    if touches_border:
        return 0.85, "Giấy tờ có thể bị cắt góc hoặc sát mép khung hình."
    return 1.0, None


def _corners_score(image: np.ndarray) -> tuple[float, str | None]:
    """Estimate whether the full document rectangle is visible."""
    h, w = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return 0.3, "Không xác định được khung giấy tờ — có thể thiếu góc."

    contours = sorted(contours, key=cv2.contourArea, reverse=True)
    best_quad = None
    image_area = float(h * w)

    for contour in contours[:8]:
        area = cv2.contourArea(contour)
        if area < image_area * 0.25:
            break
        peri = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.02 * peri, True)
        if len(approx) == 4:
            best_quad = approx.reshape(4, 2)
            break

    if best_quad is None:
        return 0.4, "Không phát hiện đủ 4 góc giấy tờ."

    margin = min(h, w) * 0.03
    xs = best_quad[:, 0]
    ys = best_quad[:, 1]
    touches_border = (
        np.any(xs < margin)
        or np.any(xs > w - margin)
        or np.any(ys < margin)
        or np.any(ys > h - margin)
    )
    coverage = (cv2.contourArea(best_quad.astype(np.float32)) / image_area)
    coverage_score = _clip01((coverage - 0.35) / 0.45)

    if touches_border:
        return _clip01(coverage_score * 0.55), "Giấy tờ có thể bị cắt góc hoặc sát mép khung hình."

    if coverage < 0.45:
        return coverage_score, "Giấy tờ chiếm diện tích nhỏ — có thể thiếu góc hoặc chụp quá xa."

    return coverage_score, None


def assess_image_quality(
    image: np.ndarray,
    config: PipelineConfig | None = None,
    *,
    corner_probe_image: np.ndarray | None = None,
) -> QualityCheckResult:
    """Assess quality on ``image``; corner detection may use ``corner_probe_image`` (pre-warp)."""
    config = config or PipelineConfig()
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image

    blur, blur_warn = _blur_score(gray)
    brightness, bright_warn = _brightness_score(gray)
    contrast, contrast_warn = _contrast_score(gray)
    glare, glare_warn = _glare_score(gray)
    corner_source = corner_probe_image if corner_probe_image is not None else image
    yolo_corners = _corners_score_yolo_layout(corner_source, config)
    if yolo_corners is not None:
        corners, corners_warn = yolo_corners
    else:
        corners, corners_warn = _corners_score(corner_source)
    screenshot, screenshot_warn = _screenshot_score(gray)

    details = QualityDetail(
        blur=round(blur, 4),
        brightness=round(brightness, 4),
        contrast=round(contrast, 4),
        glare=round(glare, 4),
        corners=round(corners, 4),
        screenshot=round(screenshot, 4),
    )

    weights = config.quality_weights
    weighted_score = (
        blur * weights["blur"]
        + brightness * weights["brightness"]
        + contrast * weights["contrast"]
        + glare * weights["glare"]
        + corners * weights["corners"]
        + screenshot * weights.get("screenshot", 0.0)
    )
    total_weight = sum(
        weights.get(key, 0.0)
        for key in ("blur", "brightness", "contrast", "glare", "corners", "screenshot")
    )
    score = weighted_score / total_weight if total_weight > 0 else 0.0

    warnings: list[str] = []
    for warning in (
        blur_warn,
        bright_warn,
        contrast_warn,
        glare_warn,
        corners_warn,
        screenshot_warn,
    ):
        if warning:
            warnings.append(warning)

    if score < config.min_quality_score:
        warnings.append(
            f"Điểm chất lượng ảnh ({score:.2f}) dưới ngưỡng {config.min_quality_score:.2f}."
        )

    return QualityCheckResult(score=round(score, 4), details=details, warnings=warnings)
