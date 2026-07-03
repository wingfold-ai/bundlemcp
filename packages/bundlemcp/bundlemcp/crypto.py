"""Encryption-at-rest for upstream OAuth tokens and client secrets (DOM-3, DEP-9).

Uses Fernet (AES-128-CBC + HMAC) via MultiFernet so keys rotate without a
migration: the FIRST configured key encrypts, ALL configured keys can decrypt.
Rotation procedure (DEP-9): prepend a new key, let re-encryption happen lazily
on next write, then drop the old key once nothing decrypts with it.

Keys come from BUNDLEMCP_TOKEN_ENCRYPTION_KEYS (urlsafe-base64 32-byte Fernet
keys). Generate one with `cryptography.fernet.Fernet.generate_key()`.
"""

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from bundlemcp.settings import Settings


class EncryptionNotConfigured(RuntimeError):
    """Raised when an upstream-oauth server needs crypto but no keys are set."""


class DecryptionError(RuntimeError):
    """Ciphertext could not be decrypted with any configured key (fail closed)."""


class TokenCipher:
    """Encrypt/decrypt secret strings. Never logged; only ciphertext is stored."""

    def __init__(self, keys: list[str]) -> None:
        if not keys:
            raise EncryptionNotConfigured(
                "BUNDLEMCP_TOKEN_ENCRYPTION_KEYS is required for upstream OAuth "
                "(generate with cryptography.fernet.Fernet.generate_key())"
            )
        # first key encrypts, all decrypt (DEP-9)
        self._fernet = MultiFernet([Fernet(k.encode()) for k in keys])

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        try:
            return self._fernet.decrypt(ciphertext.encode()).decode()
        except InvalidToken as exc:
            raise DecryptionError("token could not be decrypted with any key") from exc

    def rotate(self, ciphertext: str) -> str:
        """Re-encrypt under the current primary key (used by lazy rotation)."""
        return self._fernet.rotate(ciphertext.encode()).decode()

    def __repr__(self) -> str:  # never leak key material
        return "TokenCipher(keys=<redacted>)"


def token_cipher(settings: Settings) -> TokenCipher:
    """Build the cipher, raising EncryptionNotConfigured if no keys are set."""
    return TokenCipher(settings.token_encryption_keys)
