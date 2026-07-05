"""Encryption helpers for secrets stored at rest."""
import os

from cryptography.fernet import Fernet
from sqlalchemy import String, TypeDecorator


def _fernet() -> Fernet:
    """Build a Fernet from SECRET_ENCRYPTION_KEY.

    Resolved lazily (per read/write) rather than at import time, so the app can
    start without the key set; only encrypted columns require it.
    """
    key = os.environ.get("SECRET_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError(
            "SECRET_ENCRYPTION_KEY is not set; it is required to read or write "
            "encrypted fields. Generate one with: "
            'python -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())"'
        )
    return Fernet(key.encode())


def encrypt_secret(plaintext: str) -> str:
    """Encrypt a plaintext string to a Fernet token (for secret parameters)."""
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(token: str) -> str:
    """Decrypt a Fernet token produced by encrypt_secret."""
    return _fernet().decrypt(token.encode()).decode()


class EncryptedString(TypeDecorator):
    """A String column whose value is transparently encrypted at rest.

    Stores a Fernet token in the database; application code sees plaintext.
    The configured length must accommodate the ciphertext, which is larger
    than the plaintext.
    """

    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return _fernet().encrypt(value.encode()).decode()

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return _fernet().decrypt(value.encode()).decode()
