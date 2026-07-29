"""Private-key decryption helpers for reviewer-only eKYC data."""

from __future__ import annotations

import base64
import json
import logging
import os
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings

logger = logging.getLogger(__name__)

ENVELOPE_VERSION = 1


def _b64decode(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"))


def _b64encode(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _load_private_key_material() -> bytes | None:
    if settings.EKYC_PII_PRIVATE_KEY_PEM:
        return settings.EKYC_PII_PRIVATE_KEY_PEM.replace("\\n", "\n").encode("utf-8")
    if settings.EKYC_PII_PRIVATE_KEY_PATH:
        return Path(settings.EKYC_PII_PRIVATE_KEY_PATH).read_bytes()
    return None


def _load_public_key_material() -> bytes | None:
    if settings.EKYC_PII_PUBLIC_KEY_PEM:
        return settings.EKYC_PII_PUBLIC_KEY_PEM.replace("\\n", "\n").encode("utf-8")
    if settings.EKYC_PII_PUBLIC_KEY_PATH:
        return Path(settings.EKYC_PII_PUBLIC_KEY_PATH).read_bytes()
    return None


def encrypt_document_payload(payload: dict[str, Any]) -> str | None:
    """Encrypt a full eKYC document payload with the configured public key."""
    try:
        key_material = _load_public_key_material()
        if key_material is not None:
            public_key = serialization.load_pem_public_key(key_material)
        else:
            private_key_material = _load_private_key_material()
            if private_key_material is None:
                return None
            private_key = serialization.load_pem_private_key(
                private_key_material,
                password=None,
            )
            public_key = private_key.public_key()

        data_key = AESGCM.generate_key(bit_length=256)
        nonce = os.urandom(12)
        plaintext = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        ciphertext = AESGCM(data_key).encrypt(nonce, plaintext, None)
        encrypted_key = public_key.encrypt(
            data_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
    except Exception:
        logger.exception("Could not encrypt eKYC document payload")
        return None

    envelope = {
        "v": ENVELOPE_VERSION,
        "alg": "RSA-OAEP-SHA256+A256GCM",
        "ek": _b64encode(encrypted_key),
        "n": _b64encode(nonce),
        "ct": _b64encode(ciphertext),
    }
    return json.dumps(envelope, separators=(",", ":"))


def decrypt_document_payload(encrypted_payload: str | None) -> dict[str, Any] | None:
    """Decrypt a stored eKYC document payload with the configured private key."""
    if not encrypted_payload:
        return None

    try:
        key_material = _load_private_key_material()
        if key_material is None:
            return None
        envelope = json.loads(encrypted_payload)
        if envelope.get("v") != 1:
            return None
        private_key = serialization.load_pem_private_key(key_material, password=None)
        data_key = private_key.decrypt(
            _b64decode(envelope["ek"]),
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
        plaintext = AESGCM(data_key).decrypt(
            _b64decode(envelope["n"]),
            _b64decode(envelope["ct"]),
            None,
        )
        payload = json.loads(plaintext.decode("utf-8"))
    except Exception:
        logger.exception("Could not decrypt eKYC document payload")
        return None

    return payload if isinstance(payload, dict) else None


def _mask_identifier(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    visible = min(4, len(text))
    return f"{'*' * max(len(text) - visible, 0)}{text[-visible:]}"


def _mask_name(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    masked_words = []
    for word in text.split():
        if len(word) <= 1:
            masked_words.append("*")
        else:
            masked_words.append(f"{word[0]}{'*' * (len(word) - 1)}")
    return " ".join(masked_words)


def _mask_date(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    visible = min(2, len(text))
    return f"{'*' * max(len(text) - visible, 0)}{text[-visible:]}"


def _mask_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) <= 4:
        return "*" * len(text)
    return f"{text[:2]}{'*' * max(len(text) - 4, 3)}{text[-2:]}"


def _mask_parsed_fields(parsed_fields: dict[str, Any]) -> dict[str, Any]:
    masked = dict(parsed_fields)
    for key in ("id_number", "passport_number"):
        if key in masked:
            masked[key] = _mask_identifier(masked[key])
    if "full_name" in masked:
        masked["full_name"] = _mask_name(masked["full_name"])
    for key in ("date_of_birth", "issue_date", "expiry_date"):
        if key in masked:
            masked[key] = _mask_date(masked[key])
    for key in (
        "address",
        "place_of_origin",
        "place_of_residence",
        "issue_place",
        "surname",
        "given_names",
    ):
        if key in masked:
            masked[key] = _mask_text(masked[key])
    return masked


def mask_document_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Mask sensitive document fields before storing reviewer-safe JSON."""
    masked = dict(payload)
    parsed_fields = masked.get("parsed_fields")
    if isinstance(parsed_fields, dict):
        masked["parsed_fields"] = _mask_parsed_fields(parsed_fields)
    for key in ("admin_corrected_fields", "document_confirmed_fields", "confirmed_fields"):
        fields = masked.get(key)
        if isinstance(fields, dict):
            masked[key] = _mask_parsed_fields(fields)
    for key in (
        "full_name",
        "id_number",
        "passport_number",
        "date_of_birth",
        "address",
        "place_of_origin",
        "place_of_residence",
        "issue_date",
        "issue_place",
        "expiry_date",
    ):
        if key not in masked:
            continue
        if key in {"id_number", "passport_number"}:
            masked[key] = _mask_identifier(masked[key])
        elif key == "full_name":
            masked[key] = _mask_name(masked[key])
        elif key in {"date_of_birth", "issue_date", "expiry_date"}:
            masked[key] = _mask_date(masked[key])
        else:
            masked[key] = _mask_text(masked[key])
    return masked
