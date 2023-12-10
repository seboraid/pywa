from __future__ import annotations

import base64
import json
import dataclasses
import enum
import importlib
from typing import Any, Callable, Protocol

from cryptography.hazmat.primitives.asymmetric.padding import OAEP, MGF1, hashes
from cryptography.hazmat.primitives.ciphers import algorithms, Cipher, modes
from cryptography.hazmat.primitives.serialization import load_pem_private_key


def is_fastapi_app(app):
    """Check if the app is a FastAPI app."""
    try:
        return isinstance(app, importlib.import_module("fastapi").FastAPI)
    except ImportError:
        return False


def is_flask_app(app):
    """Check if the app is a Flask app."""
    try:
        return isinstance(app, importlib.import_module("flask").Flask)
    except ImportError:
        return False


class StrEnum(str, enum.Enum):
    def __str__(self):
        return self.value

    def __repr__(self):
        return f"{self.__class__.__name__}.{self.name}"


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class FromDict:
    """Allows to ignore extra fields when creating a dataclass from a dict."""

    # noinspection PyArgumentList
    @classmethod
    def from_dict(cls, data: dict, **kwargs):
        return cls(
            **{
                k: v
                for k, v in (data | kwargs).items()
                if k in (f.name for f in dataclasses.fields(cls))
            }
        )


class FastAPI(Protocol):
    def get(self, path: str) -> Callable:
        ...

    def post(self, path: str) -> Callable:
        ...


class Flask(Protocol):
    def route(self, rule: str, **options: Any) -> Callable:
        ...


def decrypt_request(
    encrypted_flow_data_b64: str,
    encrypted_aes_key_b64: str,
    initial_vector_b64: str,
    private_key: str,
) -> tuple[dict, bytes, bytes]:
    """
    Decrypts the request from WhatsApp Flow.

    Returns:
        decrypted_data: decrypted data from the request
        aes_key: AES key you should use to encrypt the response
        iv: initial vector you should use to encrypt the response
    """
    flow_data = base64.b64decode(encrypted_flow_data_b64)
    iv = base64.b64decode(initial_vector_b64)
    encrypted_aes_key = base64.b64decode(encrypted_aes_key_b64)
    private_key = load_pem_private_key(private_key.encode("utf-8"), password=None)
    aes_key = private_key.decrypt(
        encrypted_aes_key,
        OAEP(
            mgf=MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None
        ),
    )
    encrypted_flow_data_body = flow_data[:-16]
    encrypted_flow_data_tag = flow_data[-16:]
    decryptor = Cipher(
        algorithms.AES(aes_key), modes.GCM(iv, encrypted_flow_data_tag)
    ).decryptor()
    decrypted_data_bytes = (
        decryptor.update(encrypted_flow_data_body) + decryptor.finalize()
    )
    decrypted_data = json.loads(decrypted_data_bytes.decode("utf-8"))
    return decrypted_data, aes_key, iv


def encrypt_response(response: dict, aes_key: bytes, iv: bytes) -> str:
    """
    Encrypts the response to WhatsApp Flow.

    Returns:
        encrypted_response: encrypted response to send back to WhatsApp Flow
    """
    flipped_iv = bytearray()
    for byte in iv:
        flipped_iv.append(byte ^ 0xFF)

    encryptor = Cipher(algorithms.AES(aes_key), modes.GCM(flipped_iv)).encryptor()
    return base64.b64encode(
        encryptor.update(json.dumps(response).encode("utf-8"))
        + encryptor.finalize()
        + encryptor.tag
    ).decode("utf-8")
