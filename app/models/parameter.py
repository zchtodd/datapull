"""Shared key/value parameter behavior for JobParameter and ConnectionParameter.

Secret values are Fernet-encrypted at rest; non-secret values are stored as
plaintext so they can be shown/edited. The on-disk `value` column therefore
holds either ciphertext or plaintext depending on `is_secret`; always read and
write through the `value` property, which encodes/decodes based on is_secret.
"""
from app.extensions import db
from app.security import decrypt_secret, encrypt_secret

# Allowed value_type values. Storage is always text; the type is a hint the UI
# uses for input/validation and the runner can use to coerce when injecting.
VALUE_TYPES = ("string", "number", "boolean", "json")


class ParameterMixin:
    """Columns + encrypt/decrypt logic shared by all parameter tables."""

    key = db.Column(db.String(255), nullable=False)
    # Widened to Text so large/structured values (e.g. a JSON config blob) fit.
    _value = db.Column("value", db.Text, nullable=True)
    is_secret = db.Column(
        db.Boolean, nullable=False, default=False, server_default=db.false()
    )
    value_type = db.Column(
        db.String(16), nullable=False, default="string", server_default="string"
    )

    @property
    def value(self):
        """Plaintext value (decrypting if this is a secret), or None."""
        if self._value is None:
            return None
        return decrypt_secret(self._value) if self.is_secret else self._value

    @value.setter
    def value(self, plaintext):
        """Store plaintext, encrypting first when is_secret. Set is_secret
        BEFORE assigning value so the right encoding is chosen."""
        if plaintext is None or plaintext == "":
            self._value = None
        elif self.is_secret:
            self._value = encrypt_secret(plaintext)
        else:
            self._value = plaintext

    @property
    def has_value(self) -> bool:
        """Whether a value is stored — without decrypting (so it works even
        when the encryption key is unavailable)."""
        return self._value is not None
