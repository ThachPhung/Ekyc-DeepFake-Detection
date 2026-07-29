from ekyc_document.ocr import _sort_lines_by_position
from ekyc_document.schemas import OCRLine


def _line(text: str, left: float, top: float, right: float, bottom: float) -> OCRLine:
    return OCRLine(
        text=text,
        confidence=0.9,
        bbox=[[left, top], [right, top], [right, bottom], [left, bottom]],
    )


def test_sort_lines_by_position_keeps_same_row_left_to_right():
    lines = [
        _line("Thanh; Kim Động, Hưng Yên", 1079, 803, 1586, 860),
        _line("Đồng", 969, 794, 1082, 860),
    ]

    sorted_lines = _sort_lines_by_position(lines)

    assert [line.text for line in sorted_lines] == [
        "Đồng",
        "Thanh; Kim Động, Hưng Yên",
    ]
