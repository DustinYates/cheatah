"""Field-level encryption utilities for sensitive database fields.

Uses Fernet symmetric encryption for encrypting API keys, tokens, and secrets.
The encryption key should be stored in GCP Secret Manager in production.
"""

import logging
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)


class EncryptionError(Exception):
    """Raised when encryption/decryption fails."""
    pass


class EncryptionService:
    """Service for encrypting and decrypting sensitive data.

    Uses Fernet symmetric encryption which provides:
    - AES-128-CBC encryption
    - HMAC-SHA256 authentication
    - Timestamp-based expiration (optional)
    """

    _instance: Optional["EncryptionService"] = None
    _fernet: Optional[Fernet] = None

    def __new__(cls) -> "EncryptionService":
        """Singleton pattern to ensure consistent encryption key usage."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """Initialize the encryption service with the encryption key."""
        if self._fernet is not None:
            return

        key = self._get_encryption_key()
        if key:
            self._fernet = Fernet(key)
            logger.info("Encryption service initialized")
        else:
            logger.warning("No encryption key configured - encryption disabled")

    def _get_encryption_key(self) -> Optional[bytes]:
        """Get the encryption key from settings or environment.

        The key must be a valid 32-byte URL-safe base64-encoded key.
        Generate one with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
        """
        # Import here to avoid circular import
        from app.settings import settings

        # Check settings (which reads from FIELD_ENCRYPTION_KEY env var)
        key_str = settings.field_encryption_key

        if key_str:
            try:
                # Validate it's a proper Fernet key
                key_bytes = key_str.encode()
                Fernet(key_bytes)  # Validate key format
                return key_bytes
            except Exception as e:
                logger.error(f"Invalid FIELD_ENCRYPTION_KEY format: {e}")
                return None

        # No key configured - encryption disabled
        return None

    @property
    def is_enabled(self) -> bool:
        """Check if encryption is enabled (key is configured)."""
        return self._fernet is not None

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a plaintext string.

        Args:
            plaintext: The string to encrypt

        Returns:
            Base64-encoded encrypted string prefixed with 'enc:' marker

        Raises:
            EncryptionError: If encryption fails or is not enabled
        """
        if not plaintext:
            return plaintext

        if not self._fernet:
            # If encryption is not enabled, return plaintext with warning
            logger.warning("Encryption not enabled - storing plaintext")
            return plaintext

        try:
            encrypted_bytes = self._fernet.encrypt(plaintext.encode())
            # Prefix with 'enc:' to identify encrypted values
            return f"enc:{encrypted_bytes.decode()}"
        except Exception as e:
            raise EncryptionError(f"Failed to encrypt value: {e}") from e

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt an encrypted string.

        Args:
            ciphertext: The encrypted string (with 'enc:' prefix)

        Returns:
            Decrypted plaintext string

        Raises:
            EncryptionError: If decryption fails
        """
        if not ciphertext:
            return ciphertext

        # Check if value is encrypted (has 'enc:' prefix)
        if not ciphertext.startswith("enc:"):
            # Value is not encrypted, return as-is (backward compatibility)
            return ciphertext

        if not self._fernet:
            raise EncryptionError("Cannot decrypt: encryption key not configured")

        try:
            encrypted_bytes = ciphertext[4:].encode()  # Remove 'enc:' prefix
            decrypted_bytes = self._fernet.decrypt(encrypted_bytes)
            return decrypted_bytes.decode()
        except InvalidToken:
            raise EncryptionError("Failed to decrypt: invalid token or wrong key")
        except Exception as e:
            raise EncryptionError(f"Failed to decrypt value: {e}") from e

    def is_encrypted(self, value: str) -> bool:
        """Check if a value is already encrypted."""
        return value.startswith("enc:") if value else False


# Singleton instance
_encryption_service: Optional[EncryptionService] = None


def get_encryption_service() -> EncryptionService:
    """Get the singleton encryption service instance."""
    global _encryption_service
    if _encryption_service is None:
        _encryption_service = EncryptionService()
    return _encryption_service


def encrypt_field(value: Optional[str]) -> Optional[str]:
    """Convenience function to encrypt a field value."""
    if value is None:
        return None
    return get_encryption_service().encrypt(value)


def decrypt_field(value: Optional[str]) -> Optional[str]:
    """Convenience function to decrypt a field value."""
    if value is None:
        return None
    return get_encryption_service().decrypt(value)


def generate_encryption_key() -> str:
    """Generate a new Fernet encryption key.

    Returns:
        A URL-safe base64-encoded 32-byte key suitable for FIELD_ENCRYPTION_KEY
    """
    return Fernet.generate_key().decode()
