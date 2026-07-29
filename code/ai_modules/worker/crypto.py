"""Public-key encryption helpers for private eKYC document payloads."""

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

logger = logging.getLogger("ekyc_worker.crypto")

ENVELOPE_VERSION = 1


def _b64encode(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _load_key_material(*, env_name: str, path_env_name: str) -> bytes | None:
    value = os.getenv(env_name)
    if value:
        return value.replace("\\n", "\n").encode("utf-8")

    path_value = os.getenv(path_env_name)
    if path_value:
        return Path(path_value).read_bytes()

    return None


def encrypt_document_payload(payload: dict[str, Any]) -> str | None:
    """Encrypt a full document payload with the configured RSA public key."""
    key_material = _load_key_material(
        env_name="EKYC_PII_PUBLIC_KEY_PEM",
        path_env_name="EKYC_PII_PUBLIC_KEY_PATH",
    )
    if key_material is None:
        logger.warning("Skipping PII encryption; EKYC_PII_PUBLIC_KEY_PEM/PATH is not configured")
        return None

    public_key = serialization.load_pem_public_key(key_material)
    data_key = AESGCM.generate_key(bit_length=256)
    nonce = os.urandom(12)
    plaintext = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    ciphertext = AESGCM(data_key).encrypt(nonce, plaintext, None)
    encrypted_key = public_key.encrypt(
        data_key,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )

    envelope = {
        "v": ENVELOPE_VERSION,
        "alg": "RSA-OAEP-SHA256+A256GCM",
        "ek": _b64encode(encrypted_key),
        "n": _b64encode(nonce),
        "ct": _b64encode(ciphertext),
    }
    return json.dumps(envelope, separators=(",", ":"))
