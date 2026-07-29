"""Document dewarp via YOLO layout corner boxes with contour fallback."""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from ekyc_document.config import PipelineConfig


@dataclass(frozen=True)
class WarpResult:
    image: np.ndarray
    applied: bool
    method: str
    corners: list[list[float]] | None = None
    warning: str | None = None


def _order_corners(points: np.ndarray) -> np.ndarray:
    """Order 4 points: top-left, top-right, bottom-right, bottom-left."""
    rect = np.zeros((4, 2), dtype=np.float32)
    s = points.sum(axis=1)
    rect[0] = points[np.argmin(s)]
    rect[2] = points[np.argmax(s)]
    diff = np.diff(points, axis=1)
    rect[1] = points[np.argmin(diff)]
    rect[3] = points[np.argmax(diff)]
    return rect


def _find_contour_quad(image: np.ndarray) -> np.ndarray | None:
    h, w = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    image_area = float(h * w)
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:8]:
        area = cv2.contourArea(contour)
        if area < image_area * 0.25:
            break
        peri = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.02 * peri, True)
        if len(approx) == 4:
            return approx.reshape(4, 2).astype(np.float32)
    return None


def _perspective_warp(image: np.ndarray, corners: np.ndarray) -> np.ndarray:
    ordered = _order_corners(corners.astype(np.float32))
    width_top = np.linalg.norm(ordered[1] - ordered[0])
    width_bottom = np.linalg.norm(ordered[2] - ordered[3])
    height_left = np.linalg.norm(ordered[3] - ordered[0])
    height_right = np.linalg.norm(ordered[2] - ordered[1])
    max_width = int(max(width_top, width_bottom))
    max_height = int(max(height_left, height_right))
    max_width = max(max_width, 1)
    max_height = max(max_height, 1)

    destination = np.array(
        [
            [0, 0],
            [max_width - 1, 0],
            [max_width - 1, max_height - 1],
            [0, max_height - 1],
        ],
        dtype=np.float32,
    )
    matrix = cv2.getPerspectiveTransform(ordered, destination)
    return cv2.warpPerspective(image, matrix, (max_width, max_height))


def _detect_corners_yolo_layout(image: np.ndarray, config: PipelineConfig) -> np.ndarray | None:
    model_path = config.yolo_layout_model
    if model_path is None or not model_path.is_file():
        return None

    from ekyc_document.ocr_stack.layout_detect import YOLOLayoutDetector, extract_layout_corners

    fields = YOLOLayoutDetector(config).detect(image)
    return extract_layout_corners(fields)


def warp_document(image: np.ndarray, config: PipelineConfig | None = None) -> WarpResult:
    """Flatten skewed CCCD captures using layout-detected corners or contour fallback."""
    config = config or PipelineConfig()
    if not config.document_warp_enabled:
        return WarpResult(image=image, applied=False, method="disabled")

    corners = _detect_corners_yolo_layout(image, config)
    method = "yolo_layout_corners"
    if corners is None and config.document_warp_fallback == "contour":
        corners = _find_contour_quad(image)
        method = "contour"

    if corners is None:
        return WarpResult(
            image=image,
            applied=False,
            method="none",
            warning="Không phát hiện đủ 4 góc giấy tờ để bẻ phẳng.",
        )

    warped = _perspective_warp(image, corners)
    corner_list = corners.tolist()
    warning = None
    if method == "contour":
        warning = "Đã bẻ phẳng giấy tờ bằng contour fallback (YOLO layout chưa detect đủ 4 góc)."
    return WarpResult(
        image=warped,
        applied=True,
        method=method,
        corners=corner_list,
        warning=warning,
    )
