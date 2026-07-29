"""Read and print a private PII record from code/data/private/records/."""

from __future__ import annotations

import argparse
import json
import sys

from ekyc_document.config import PipelineConfig
from ekyc_document.private_store import PrivateRecordNotFound, PrivateRecordStore


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Xem bản ghi PII theo record_id"
    )
    parser.add_argument("record_id", nargs="?", help="UUID bản ghi (vd. từ pipeline output)")
    parser.add_argument(
        "--list",
        action="store_true",
        help="Liệt kê các file .json trong thư mục private",
    )
    args = parser.parse_args()

    config = PipelineConfig()
    records_dir = config.private_storage_dir / "records"

    if args.list:
        files = sorted(records_dir.glob("*.json"))
        if not files:
            print(f"Không có file nào trong {records_dir}")
            return
        print(f"Thư mục: {records_dir.resolve()}\n")
        for path in files:
            print(path.stem)
        return

    if not args.record_id:
        parser.error("Cần record_id hoặc dùng --list")

    try:
        data = PrivateRecordStore(config).load_record(args.record_id)
    except PrivateRecordNotFound as exc:
        print(f"Lỗi: {exc}", file=sys.stderr)
        print(f"Gợi ý: python -m ekyc_document.view_record --list", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
