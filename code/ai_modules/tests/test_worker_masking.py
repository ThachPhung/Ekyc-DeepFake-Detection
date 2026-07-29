from worker.masking import mask_document_payload


def test_mask_document_payload_redacts_top_level_ocr_fields():
    payload = {
        "full_name": "NGUYEN VAN A",
        "id_number": "001201123456",
        "date_of_birth": "01/01/2001",
        "address": "123 Nguyen Trai, Ha Noi",
        "issue_date": "29/09/2022",
        "document_type": "CCCD",
    }

    masked = mask_document_payload(payload)

    assert masked["id_number"] == "********3456"
    assert masked["full_name"] == "N***** V** *"
    assert masked["date_of_birth"] == "********01"
    assert masked["address"] == "12*******************oi"
    assert masked["issue_date"] == "********22"
    assert masked["document_type"] == "CCCD"


def test_mask_document_payload_redacts_nested_parsed_fields():
    payload = {
        "document_type": "CCCD",
        "parsed_fields": {
            "id_number": "012345678901",
            "passport_number": "B1234567",
            "full_name": "TRAN THI B",
            "date_of_birth": "2000-01-31",
            "place_of_origin": "Da Nang",
            "place_of_residence": "Quan 1, TP HCM",
            "issue_place": "Cuc Canh sat",
            "nationality": "Viet Nam",
            "extra": {"raw": "kept as-is"},
        },
    }

    masked = mask_document_payload(payload)
    fields = masked["parsed_fields"]

    assert fields["id_number"] == "********8901"
    assert fields["passport_number"] == "****4567"
    assert fields["full_name"] == "T*** T** *"
    assert fields["date_of_birth"] == "********31"
    assert fields["place_of_origin"] == "Da***ng"
    assert fields["place_of_residence"] == "Qu**********CM"
    assert fields["issue_place"] == "Cu********at"
    assert fields["nationality"] == "Viet Nam"
    assert fields["extra"] == {"raw": "kept as-is"}
