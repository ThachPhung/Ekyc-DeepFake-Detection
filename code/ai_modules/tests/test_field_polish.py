from ekyc_document.field_polish import (
    apply_mrz_name_correction,
    correct_id_number_from_mrz,
    correct_full_name_from_mrz,
    polish_extracted_fields,
)
from ekyc_document.parser import parse_mrz_id_numbers, parse_mrz_name_tokens
from ekyc_document.schemas import ParsedFields


def test_parse_mrz_name_tokens_thach():
    back = "PHUNG<<VAN<THACH<<<<<<<<<<<<<<"
    assert parse_mrz_name_tokens(back) == ["PHUNG", "VAN", "THACH"]


def test_parse_mrz_name_tokens_doan_fixture():
    back = (
        "IDVNM2010007163031201000716<<3\n"
        "0105307M2605306VNM<<<<<<<<<<<8\n"
        "LUONG<<QU0C<D0AN<<<<<<<<<<<<<<"
    )
    assert parse_mrz_name_tokens(back) == ["LUONG", "QUOC", "DOAN"]


def test_correct_full_name_from_mrz_fixes_phung_diacritics():
    back = "PHUNG<<VAN<THACH<<<<<<<<<<<<<<"
    assert correct_full_name_from_mrz("Phúng Văn Thạch", back) == "Phùng Văn Thạch"
    assert correct_full_name_from_mrz("Phùng Văn Thạch", back) == "Phùng Văn Thạch"


def test_correct_full_name_from_mrz_skips_when_word_count_mismatch():
    back = "PHUNG<<VAN<THACH<<<<<<<<<<<<<<"
    assert correct_full_name_from_mrz("Phúng Văn", back) == "Phúng Văn"


def test_apply_mrz_name_correction_updates_fields():
    fields = ParsedFields(full_name="Phúng Văn Thạch", id_number="038202012897")
    corrected = apply_mrz_name_correction(fields, "PHUNG<<VAN<THACH<<<<<<<<<<<<<<")
    assert corrected is not None
    assert corrected.full_name == "Phùng Văn Thạch"
    assert corrected.id_number == "038202012897"


def test_parse_mrz_id_numbers_reads_new_cccd_id_line():
    back = "IDVNM038202012897<<8\n0201062M2701068VNM<<<<<<<<<<<4"
    assert parse_mrz_id_numbers(back) == ["038202012897"]


def test_parse_mrz_id_numbers_prefers_embedded_12_digit_cccd():
    back = "IDVNM2010007163031201000716<<3"
    assert parse_mrz_id_numbers(back)[0] == "031201000716"


def test_correct_id_number_from_mrz_replaces_demographic_mismatch():
    fields = ParsedFields(
        id_number="003820201289",
        full_name="Phùng Văn Thạch",
        date_of_birth="06/01/2002",
        sex="Nam",
        extra={"ocr_locked_fields": ["id_number", "full_name"]},
    )
    back = (
        "IDVNM038202012897<<8\n"
        "0201062M2701068VNM<<<<<<<<<<<4\n"
        "PHUNG<<VAN<THACH<<<<<<<<<<<<<<"
    )

    corrected = correct_id_number_from_mrz(fields, back)

    assert corrected is not None
    assert corrected.id_number == "038202012897"
    assert corrected.extra["id_number_corrected_from_mrz"] is True


def test_polish_fixes_quoc_diacritics_in_name():
    raw = ParsedFields(full_name="LƯƠNG QUÓC DOÀN")
    polished = polish_extracted_fields(raw)
    assert polished is not None
    assert polished.full_name == "Lương Quốc Đoàn"


def test_polish_fixes_name_without_diacritics_using_token_map():
    raw = ParsedFields(full_name="PHUNG VAN THACH")
    polished = polish_extracted_fields(raw)
    assert polished is not None
    assert polished.full_name == "Phùng Văn Thạch"


def test_polish_fixes_ha_noi_place():
    raw = ParsedFields(place_of_origin="Ngoc Thuy, Long Bien, Ha Noi")
    polished = polish_extracted_fields(raw)
    assert polished is not None
    assert polished.place_of_origin == "Ngọc Thụy, Long Biên, Hà Nội"

    raw = ParsedFields(
        id_number="001181039694",
        full_name="NGÔ LAN PHU'ONG",
        date_of_birth="31/05/1981",
        sex="N",
        nationality="Việt Nam",
        place_of_origin="Ngoc Thuy, Long Biên, Hà Nội",
        place_of_residence="51 Cra Đông, 51 Cra Đông",
        issue_date="29/09/2022",
        issue_place="CUC TRUÒNG CC CÀNH SÁT, QUAN LY HANH CHÍNH VÈ TRAT TU XÃ HQI",
        expiry_date="31/05/2041",
    )

    polished = polish_extracted_fields(raw)
    assert polished is not None
    assert polished.full_name == "Ngô Lan Phương"
    assert polished.sex == "Nữ"
    assert polished.place_of_origin == "Ngọc Thụy, Long Biên, Hà Nội"
    assert polished.place_of_residence == "51 Cra Đông"
    assert (
        polished.issue_place
        == "Cục Cảnh sát quản lý hành chính về trật tự xã hội"
    )
