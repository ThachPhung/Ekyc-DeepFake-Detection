from ekyc_document.parser import detect_document_type, parse_document


CCCD_SAMPLE = """
CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM
CĂN CƯỚC CÔNG DÂN
Số / No.: 079203012345
Họ và tên / Full name:
NGUYỄN VĂN A
Ngày sinh / Date of birth: 01/01/1990
Giới tính / Sex: Nam
Quốc tịch / Nationality: Việt Nam
Quê quán / Place of origin: TP. Hồ Chí Minh
Nơi thường trú / Place of residence: Quận 1, TP. Hồ Chí Minh
Ngày cấp / Date of issue: 01/01/2021
Ngày hết hạn / Date of expiry: 01/01/2031
"""

GPLX_SAMPLE = """
GIẤY PHÉP LÁI XE
Số: 079203012345
Họ và tên: TRẦN THỊ B
Ngày sinh: 15/05/1988
Hạng: B2
"""

PASSPORT_SAMPLE = """
PASSPORT
Surname: NGUYEN
Given names: VAN C
Nationality: VIET NAM
Date of birth: 20/03/1992
Passport No: C1234567
"""


def test_detect_cccd():
    assert detect_document_type(CCCD_SAMPLE) == "CCCD"


def test_detect_gplx():
    assert detect_document_type(GPLX_SAMPLE) == "GPLX"


def test_detect_passport():
    assert detect_document_type(PASSPORT_SAMPLE) == "PASSPORT"


def test_parse_cccd_fields():
    result = parse_document(CCCD_SAMPLE)
    assert result.document_type == "CCCD"
    assert result.fields.id_number == "079203012345"
    assert result.fields.full_name is not None
    assert "NGUYỄN" in result.fields.full_name.upper()
    assert result.fields.issue_date == "01/01/2021"
    assert result.fields.expiry_date == "01/01/2031"


def test_parse_cccd_multiline_residence():
    sample = """
    CĂN CƯỚC CÔNG DÂN
    Số / No.: 079203012345
    Họ và tên / Full name:
    NGUYỄN VĂN A
    Ngày sinh / Date of birth: 01/01/1990
    Nơi thường trú / Place of residence:
    Số 1 Nguyễn Huệ, Phường Bến Nghé,
    Quận 1, TP. Hồ Chí Minh
    Có giá trị đến / Date of expiry: 01/01/2031
    """
    result = parse_document(sample, forced_type="CCCD")
    assert result.fields.place_of_residence is not None
    assert "Nguyễn Huệ" in result.fields.place_of_residence
    assert "Quận 1" in result.fields.place_of_residence


def test_parse_cccd_origin_drops_expiry_ocr_fragments():
    sample = """
    CĂN CƯỚC CÔNG DÂN
    Quê quán / Place of origin:
    Thanh; Kim Động, Hưng Yên
    Co
    ni den;
    Nơi thường trú / Place of residence: 39/8/267 Lê
    Daigtat ưrpiry 30/05/2026
    """
    result = parse_document(sample, forced_type="CCCD")
    assert result.fields.place_of_origin == "Thanh, Kim Động, Hưng Yên"
    assert "Co" not in result.fields.place_of_origin
    assert "den" not in result.fields.place_of_origin.lower()


def test_parse_cccd_back_side_issue_fields():
    sample = """
    Đặc điểm nhận dạng / Personal identification
    Ngày; tháng; năm
    Date,
    month; yearo2/07/2021
    CUC TRƯỞNG CUC CANH SÁT
    QUAN LÝ HÀNH CHÍNH VỀ TRẬT TỰ XÃ HỘI
    """
    result = parse_document(sample, forced_type="CCCD")
    assert result.fields.issue_date == "02/07/2021"
    assert "CUC CANH SÁT" in result.fields.issue_place


def test_parse_cccd_multiline_residence():
    sample = """
CĂN CƯỚC CÔNG DÂN
Số / No.: 031201000716
Họ và tên / Full name:
LƯƠNG QUỐC ĐOÀN
Nơi thường trú / Place of residence:
39/8/267 Lê
Trọng Tấn, Sơn Kỳ
Tân Phú, TP. Hồ Chí Minh
Ngày hết hạn / Date of expiry: 30/05/2026
"""

    result = parse_document(sample)

    assert result.fields.place_of_residence is not None
    assert "39/8/267 Lê" in result.fields.place_of_residence
    assert "Trọng Tấn" in result.fields.place_of_residence
    assert "Tân Phú" in result.fields.place_of_residence


def test_parse_cccd_filters_expiry_noise_from_addresses():
    sample = """
CĂN CƯỚC CÔNG DÂN
Số / No.: 031201000716
Họ và tên / Full name:
LƯƠNG QUỐC ĐOÀN
Quê quán / Place of origin:
Thanh; Kim Động, Hưng Yên
Co
Co, ni den;
Nơi thường trú / Place of residence:
39/8/267 Lê
Daigtat ưrpiry 30/05/2026
Thánh, Máy Chai, Ngô Quyền, HP
Đồng, giá
Đồng
Ngày hết hạn / Date of expiry: 30/05/2026
"""

    result = parse_document(sample)

    assert result.fields.place_of_origin == "Thanh, Kim Động, Hưng Yên"
    assert result.fields.place_of_residence is not None
    assert "39/8/267 Lê" in result.fields.place_of_residence
    assert "Máy Chai" in result.fields.place_of_residence
    assert "expiry" not in result.fields.place_of_residence.lower()
    assert "30/05/2026" not in result.fields.place_of_residence
    assert "Co" not in result.fields.place_of_origin
    assert "Đồng, giá" not in result.fields.place_of_residence
    assert not result.fields.place_of_residence.endswith("Đồng")


def test_parse_cccd_filters_broken_origin_label_prefix():
    sample = """
CĂN CƯỚC CÔNG DÂN
Số / No.: 031201000716
Họ và tên / Full name:
LƯƠNG QUỐC ĐOÀN
Quê quán / Place of origin:
c{ oigin, Bach Thuân; Vu Thư , Thái Binh
Nơi thường trú / Place of residence:
39/8/267 Lê
"""

    result = parse_document(sample)

    assert result.fields.place_of_origin == "Bach Thuân, Vũ Thư, Thái Bình"
    assert "oigin" not in result.fields.place_of_origin.lower()
    assert "c{" not in result.fields.place_of_origin


def test_parse_cccd_expiry_date_is_not_issue_date():
    sample = """
CĂN CƯỚC CÔNG DÂN
Số / No.: 031201000716
Họ và tên / Full name:
LƯƠNG QUỐC ĐOÀN
Ngày sinh / Date of birth: 30/05/2001
Nơi thường trú / Place of residence:
39/8/267 Lê
Ngày hết hạn / Date of expiry: 30/05/2026
"""

    result = parse_document(sample)

    assert result.fields.date_of_birth == "30/05/2001"
    assert result.fields.issue_date is None
    assert result.fields.expiry_date == "30/05/2026"


def test_parse_cccd_back_side_does_not_require_id_number():
    result = parse_document(
        """
Đặc điểm nhận dạng: Nốt ruồi cạnh mũi
Ngày cấp: 29/09/2022
Nơi cấp: Cục Cảnh sát quản lý hành chính về trật tự xã hội
""",
        forced_type="CCCD",
        side="back",
    )

    assert result.document_type == "CCCD"
    assert result.fields.id_number is None
    assert result.fields.full_name is None
    assert result.fields.date_of_birth is None
    assert result.fields.issue_date == "29/09/2022"
    assert result.fields.extra["issued_by"] is not None
    assert "Cục Cảnh sát" in result.fields.extra["issued_by"]
    assert not any("số CCCD" in warning for warning in result.warnings)


def test_parse_cccd_back_finds_issuing_authority_without_label():
    result = parse_document(
        """
Đặc điểm nhận dạng / Personal identification:
sẹo nhỏ trên trán
Cục Cảnh sát quản lý hành chính về trật tự xã hội
Ngày cấp / Date of issue: 29/09/2022
""",
        forced_type="CCCD",
        side="back",
    )

    assert result.fields.issue_date == "29/09/2022"
    assert result.fields.extra["issued_by"] is not None
    assert "Cục Cảnh sát" in result.fields.extra["issued_by"]


def test_parse_passport_number():
    result = parse_document(PASSPORT_SAMPLE)
    assert result.document_type == "PASSPORT"
    assert result.fields.passport_number == "C1234567"


DOAN_LIKE_OCR = """
CĂN CƯỚC CÔNG DÂN
Số / No.: 031201000716
Họ và tên / Full name:
LU'ONG QUOC DOAN
Ngày sinh / Date of birth: 30/05/2001
Giới tính / Sex: Nam Quoc tich / Nationality: Vit Nam
Quê quán / Place of origin:
Dông Thanh, Kim Dông, Hurng Yên
ofbapiry
Thánh Tông, Máy Chai, Ngô Quyěn, HP
"""


DOAN_REAL_OCR = """
CĂN CUÓC CÔNG DÂN
só/No: 031201000716
Ho và tên I Full name:
LU'ONG QUÓC DOÀN
Ngày sinh / Date of birth: 30/05/2001
Giói tính / Sex: Nam Quôc tch / Nationality: Vit Nam
Quê quán I Place of origin:
0202
Noihiie  o e   e
Đồng Thanh, Kim Đong, Hung Yên
afuxpiry
Thánh Tông, Máy Chai, Ngô Quyn, HP
"""


TEST_KHOI_OCR = """
CĂN CƯỚC CÔNG DÂN
sóI No. 001060018452
Ho và tên / Ful name NGUYÊN HUY KHÔI
Ngày sinh / Date of birth. 12/05/1960
Giói tinh/ Sex Nam Quóc tch / Naliunality. Viêt Nam
Quê quán / Place of onigin
Bách Thun, Vū Thư, Thái Binh
Có gia trj dón:
Noi thung trú / Placs of residence44 Hàng Ngang
Khong thor han
Háng Đào, Hoàn Kim, Hà Ni
"""


DUONG_REAL_OCR = """
CĂN CU'ÓC CÔNG DÂN
S/N:001064010140
Ho và tên / Full name:
VÜ HÀ DU'ONG
Ngày šinh / Date of birth:
27/07/1964
Giói tinh / Sex: Nam Quóc tich/ Nationelity Viêt Nam
Hong Phong, Thanh Mien, Hai Duong
Quê quán / Place of origin:
Co gia t den:27/07/2024
Noi thuòng trú / Place of residence Só 43 Hàng Bac
Hàng Bąc, Hoàn Kim, Hà Ni
"""


def test_parse_duong_sample_extracts_origin_and_clean_nationality():
    result = parse_document(DUONG_REAL_OCR, forced_type="CCCD")

    assert result.fields.sex == "Nam"
    assert result.fields.nationality == "Việt Nam"
    assert result.fields.place_of_origin == "Hồng Phong, Thanh Miện, Hải Dương"
    assert "Số 43 Hàng Bắc" in (result.fields.place_of_residence or "")
    assert "Hoàn Kiếm" in (result.fields.place_of_residence or "")
    assert "Hà Nội" in (result.fields.place_of_residence or "")


def test_parse_khoi_sample_extracts_sex_and_correct_places():
    result = parse_document(TEST_KHOI_OCR, forced_type="CCCD")

    assert result.fields.sex == "Nam"
    assert result.fields.nationality == "Việt Nam"
    assert result.fields.place_of_origin == "Bách Thuận, Vũ Thư, Thái Bình"
    assert result.fields.place_of_residence == "44 Hàng Ngang, Hàng Đào, Hoàn Kiếm, Hà Nội"


def test_parse_doan_real_ocr_front_text():
    result = parse_document(DOAN_REAL_OCR, forced_type="CCCD")

    assert result.fields.place_of_origin == "Đông Thanh, Kim Động, Hưng Yên"
    assert "0202" not in (result.fields.place_of_origin or "")
    assert "Noihiie" not in (result.fields.place_of_origin or "")
    assert result.fields.place_of_residence == "Thánh Tông, Máy Chai, Ngô Quyền, HP"
    assert result.fields.sex == "Nam"
    assert result.fields.nationality == "Việt Nam"


def test_parse_doan_like_ocr_extracts_origin_residence_and_splits_sex():
    result = parse_document(DOAN_LIKE_OCR, forced_type="CCCD")

    assert result.fields.id_number == "031201000716"
    assert result.fields.sex == "Nam"
    assert result.fields.nationality is not None
    assert "Việt Nam" in result.fields.nationality
    assert result.fields.place_of_origin is not None
    assert "Đông Thanh" in result.fields.place_of_origin
    assert "Kim Động" in result.fields.place_of_origin
    assert "Hưng Yên" in result.fields.place_of_origin
    assert "ofbapiry" not in (result.fields.place_of_origin or "").lower()
    assert result.fields.place_of_residence is not None
    assert "Máy Chai" in result.fields.place_of_residence
    assert "Ngô Quyền" in result.fields.place_of_residence


def test_parse_cccd_sex_when_value_is_on_next_nationality_line():
    sample = """
CĂN CƯỚC CÔNG DÂN
Số / No.: 038202012897
Ngày sinh / Date of birth:
06/01/2002
Giói tinh / Sex:
Nam Quôc tich / Nationality: Viêt Nam
"""
    result = parse_document(sample, forced_type="CCCD")
    assert result.fields.sex == "Nam"
    assert result.fields.nationality == "Việt Nam"


def test_parse_cccd_corrects_thach_residence_variants():
    sample = """
CĂN CƯỚC CÔNG DÂN
Nơi thường trú / Place of residence: Thôn Bc Son
Hong Phu, Hong Hóa, Thanh Hóa
"""
    result = parse_document(sample, forced_type="CCCD")
    assert result.fields.place_of_residence == "Thôn Bắc Sơn, Hoằng Phụ, Hoằng Hóa, Thanh Hóa"


def test_parse_cccd_origin_filters_ofbapiry_noise():
    sample = """
CĂN CƯỚC CÔNG DÂN
Quê quán / Place of origin:
Dông Thanh, Kim Dông, Hurng Yên
ofbapiry
"""
    result = parse_document(sample, forced_type="CCCD")
    assert result.fields.place_of_origin == "Đông Thanh, Kim Động, Hưng Yên"
    assert "ofbapiry" not in (result.fields.place_of_origin or "").lower()


def test_parse_cccd_residence_fallback_without_label():
    sample = """
CĂN CƯỚC CÔNG DÂN
Quê quán / Place of origin:
Thanh, Kim Động, Hưng Yên
Thánh Tông, Máy Chai, Ngô Quyền, HP
"""
    result = parse_document(sample, forced_type="CCCD")
    assert result.fields.place_of_residence is not None
    assert "Máy Chai" in result.fields.place_of_residence


def test_parse_cccd_back_normalizes_issue_place_from_ocr():
    result = parse_document(
        """
Đặc điểm nhận dạng / Personal identification:
Măt nhièu seo cham
Ngày, tháng, năm / Date, month, year: 29/09/2022
CUC TRUÒNG CC CÀNH SÁT
QUAN LY HANH CHÍNH VÈ TRAT TU XÃ HQI
""",
        forced_type="CCCD",
        side="back",
    )

    assert result.fields.issue_place == "Cục Cảnh sát quản lý hành chính về trật tự xã hội"
    assert result.fields.extra["issued_by"] == result.fields.issue_place


def test_merge_parsed_fields_uses_back_issue_place():
    from ekyc_document.parser import merge_parsed_fields
    from ekyc_document.schemas import ParsedFields

    front = ParsedFields(id_number="031201000716", full_name="LƯƠNG QUỐC ĐOÀN")
    back = ParsedFields(
        issue_date="29/09/2022",
        extra={"issued_by": "Cục Cảnh sát quản lý hành chính về trật tự xã hội"},
    )

    merged = merge_parsed_fields(front, back)

    assert merged.issue_date == "29/09/2022"
    assert merged.issue_place is not None
    assert "Cục Cảnh sát" in merged.issue_place


def test_parse_cccd_name_before_full_name_label():
    result = parse_document(
        """
001163006372
NGUYỄN THỊ NGA
Ho và tên / Full name
Ngày sinh / Date of bith: 08/08/1963
Giới tính / Sex: Nữ
""",
        forced_type="CCCD",
    )

    assert result.fields.full_name is not None
    assert "NGUYỄN" in result.fields.full_name.upper()
    assert "NGA" in result.fields.full_name.upper()
    assert "NGÀY SINH" not in result.fields.full_name.upper()
    assert "DATE OF" not in result.fields.full_name.upper()


def test_parse_cccd_short_name_inline_with_label():
    result = parse_document(
        """
CĂN CƯỚC CÔNG DÂN
Số / No.: 001064010140
Họ và tên / Full name: VŨ HÀ DƯƠNG
Ngày sinh / Date of birth: 27/07/1964
Giới tính / Sex: Nam
""",
        forced_type="CCCD",
    )

    assert result.fields.full_name == "VŨ HÀ DƯƠNG"


def test_parse_cccd_long_name_on_lines_below_label():
    result = parse_document(
        """
CĂN CƯỚC CÔNG DÂN
Số / No.: 079203012345
Họ và tên / Full name
NGUYỄN THỊ THANH
TẠ BÍCH HƯƠNG
Ngày sinh / Date of birth: 01/01/1990
Giới tính / Sex: Nữ
""",
        forced_type="CCCD",
    )

    assert result.fields.full_name is not None
    assert "NGUYỄN THỊ THANH" in result.fields.full_name.upper()
    assert "TẠ BÍCH HƯƠNG" in result.fields.full_name.upper()
