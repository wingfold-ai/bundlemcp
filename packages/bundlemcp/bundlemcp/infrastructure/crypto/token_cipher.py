from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from bundlemcp.application.contracts.secret_cipher import DecryptionError
from bundlemcp.application.settings.settings import Settings
from bundlemcp.infrastructure.crypto.encryption_not_configured import EncryptionNotConfigured


class TokenCipher:
    """Encrypt/decrypt secret strings. Never logged; only ciphertext is stored."""

    def __init__(self, keys: list[str]) -> None:
        if not keys:
            raise EncryptionNotConfigured(
                "BUNDLEMCP_TOKEN_ENCRYPTION_KEYS is required for upstream OAuth "
                "(generate with cryptography.fernet.Fernet.generate_key())"
            )
        # first key encrypts, all decrypt
        self._primary = Fernet(keys[0].encode())
        self._fernet = MultiFernet([Fernet(k.encode()) for k in keys])

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        try:
            return self._fernet.decrypt(ciphertext.encode()).decode()
        except InvalidToken as exc:
            raise DecryptionError("token could not be decrypted with any key") from exc

    def is_current(self, ciphertext: str) -> bool:
        try:
            self._primary.decrypt(ciphertext.encode())
        except InvalidToken:
            return False
        return True

    def reencrypt(self, ciphertext: str) -> str:
        try:
            return self._fernet.rotate(ciphertext.encode()).decode()
        except InvalidToken as exc:
            raise DecryptionError("token could not be decrypted with any key") from exc

    def __repr__(self) -> str:  # never leak key material
        return "TokenCipher(keys=<redacted>)"


def token_cipher(settings: Settings) -> TokenCipher:
    """Build the cipher, raising EncryptionNotConfigured if no keys are set."""
    return TokenCipher(settings.token_encryption_keys)
