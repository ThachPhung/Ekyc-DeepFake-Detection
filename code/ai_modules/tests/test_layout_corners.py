from __future__ import annotations

import numpy as np

from ekyc_document.ocr_stack.layout_detect import (
    LayoutField,
    extract_layout_corners,
    has_all_layout_corners,
    is_layout_corner_label,
    normalize_layout_corner_key,
)


def test_corner_label_aliases():
    assert normalize_layout_corner_key("top_left") == "tl"
    assert normalize_layout_corner_key("TOP_RIGHT") == "tr"
    assert normalize_layout_corner_key("corner_bl") == "bl"
    assert normalize_layout_corner_key("bottom_right") == "br"
    assert normalize_layout_corner_key("id_number") is None
    assert is_layout_corner_label("bottom_left") is True


def test_extract_layout_corners_from_top_left_labels():
    fields = [
        LayoutField(label="top_left", bbox=(10, 10, 30, 30), confidence=0.9),
        LayoutField(label="top_right", bbox=(700, 12, 720, 32), confidence=0.91),
        LayoutField(label="bottom_right", bbox=(698, 430, 718, 450), confidence=0.88),
        LayoutField(label="bottom_left", bbox=(12, 428, 32, 448), confidence=0.87),
    ]
    corners = extract_layout_corners(fields)
    assert corners is not None
    assert corners.shape == (4, 2)
    assert has_all_layout_corners(fields) is True
    assert corners[0][0] < corners[1][0]
    assert corners[0][1] < corners[3][1]


def test_extract_layout_corners_picks_highest_confidence():
    fields = [
        LayoutField(label="top_left", bbox=(10, 10, 30, 30), confidence=0.5),
        LayoutField(label="top_left", bbox=(12, 12, 28, 28), confidence=0.95),
        LayoutField(label="top_right", bbox=(700, 12, 720, 32), confidence=0.9),
        LayoutField(label="bottom_right", bbox=(698, 430, 718, 450), confidence=0.9),
        LayoutField(label="bottom_left", bbox=(12, 428, 32, 448), confidence=0.9),
    ]
    corners = extract_layout_corners(fields)
    assert corners is not None
    assert corners[0][0] == 20.0
    assert corners[0][1] == 20.0


def test_extract_layout_corners_missing_one_returns_none():
    fields = [
        LayoutField(label="top_left", bbox=(10, 10, 30, 30), confidence=0.9),
        LayoutField(label="top_right", bbox=(700, 12, 720, 32), confidence=0.91),
        LayoutField(label="bottom_right", bbox=(698, 430, 718, 450), confidence=0.88),
    ]
    assert extract_layout_corners(fields) is None
    assert has_all_layout_corners(fields) is False
