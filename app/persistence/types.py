"""Custom SQLAlchemy types for the application."""

from typing import Optional

from sqlalchemy import String, Text, TypeDecorator

from app.core.encryption import decrypt_field, encrypt_field


class EncryptedString(TypeDecorator):
    """SQLAlchemy type for transparently encrypting/decrypting string fields.

    Usage:
        api_key = Column(EncryptedString(255), nullable=True)

    The value is encrypted before being stored in the database and
    automatically decrypted when read. Uses 'enc:' prefix to identify
    encrypted values, allowing backward compatibility with existing
    unencrypted data.
    """

    impl = String
    cache_ok = True

    def __init__(self, length: Optional[int] = None):
        """Initialize with optional length constraint.

        Note: Encrypted values are longer than plaintext due to base64 encoding
        and the 'enc:' prefix. A 255-char plaintext becomes ~400 chars encrypted.
        The impl length should account for this expansion.
        """
        # Encrypted values are roughly 1.4x longer + 4 chars for 'enc:' prefix + Fernet overhead
        # For safety, use 3x the requested length or a minimum of 512
        if length:
            super().__init__(max(length * 3, 512))
        else:
            super().__init__(512)
        self._original_length = length

    def process_bind_param(self, value: Optional[str], dialect) -> Optional[str]:
        """Encrypt value before storing in database."""
        if value is None:
            return None
        return encrypt_field(value)

    def process_result_value(self, value: Optional[str], dialect) -> Optional[str]:
        """Decrypt value when reading from database."""
        if value is None:
            return None
        return decrypt_field(value)


class EncryptedText(TypeDecorator):
    """SQLAlchemy type for encrypting longer text fields (tokens, etc.).

    Same as EncryptedString but uses Text as the underlying type
    for unlimited length storage.
    """

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: Optional[str], dialect) -> Optional[str]:
        """Encrypt value before storing in database."""
        if value is None:
            return None
        return encrypt_field(value)

    def process_result_value(self, value: Optional[str], dialect) -> Optional[str]:
        """Decrypt value when reading from database."""
        if value is None:
            return None
        return decrypt_field(value)
