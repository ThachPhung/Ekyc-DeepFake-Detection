from __future__ import annotations

from ekyc_document.ocr_stack.layout_detect import (
    LAYOUT_FIELD_ALIASES,
    YOLO_LAYOUT_CLASS_NAMES,
    is_layout_ocr_field_label,
    is_layout_skip_label,
    normalize_layout_field_label,
)


def test_yolo_class_names_are_mapped_or_skipped():
    for label in YOLO_LAYOUT_CLASS_NAMES:
        if is_layout_skip_label(label):
            continue
        canonical = normalize_layout_field_label(label)
        assert is_layout_ocr_field_label(label) or canonical == "portrait"


def test_front_field_aliases():
    assert normalize_layout_field_label("id") == "id_number"
    assert normalize_layout_field_label("name") == "full_name"
    assert normalize_layout_field_label("birthday") == "date_of_birth"
    assert normalize_layout_field_label("gender") == "sex"
    assert normalize_layout_field_label("address") == "place_of_residence"
    assert normalize_layout_field_label("birthplace") == "place_of_origin"
    assert normalize_layout_field_label("expiry") == "expiry_date"
    assert normalize_layout_field_label("nationality") == "nationality"
    assert normalize_layout_field_label("issue_date") == "issue_date"


def test_back_field_aliases():
    assert normalize_layout_field_label("id_back") == "mrz"
    assert is_layout_ocr_field_label("id_back") is True


def test_skip_labels():
    for label in (
        "feature",
        "new_back_cccd",
        "new_front_cccd",
        "old_back_cccd",
        "old_front_cccd",
        "top_left",
        "top_right",
        "bottom_left",
        "bottom_right",
        "portrait",
    ):
        assert is_layout_skip_label(label) or label == "portrait"


def test_all_aliases_point_to_known_targets():
    for raw, canonical in LAYOUT_FIELD_ALIASES.items():
        assert raw == raw.lower()
        assert canonical == canonical.lower()
        assert canonical
