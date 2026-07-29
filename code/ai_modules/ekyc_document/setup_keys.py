"""Generate internal API key for backend ↔ AI service communication."""

from __future__ import annotations

import secrets


def generate_internal_api_key() -> str:
    return secrets.token_urlsafe(32)


def main() -> None:
    internal_api_key = generate_internal_api_key()
    print("# Thêm dòng sau vào file .env ở thư mục gốc project:\n")
    print(f"EKYC_INTERNAL_API_KEY={internal_api_key}")
    print("\n# Sau đó khởi động lại AI service.")


if __name__ == "__main__":
    main()
