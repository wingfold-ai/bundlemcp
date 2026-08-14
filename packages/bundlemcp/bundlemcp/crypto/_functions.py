from bundlemcp.crypto.token_cipher import TokenCipher
from bundlemcp.settings import Settings


def token_cipher(settings: Settings) -> TokenCipher:
    """Build the cipher, raising EncryptionNotConfigured if no keys are set."""
    return TokenCipher(settings.token_encryption_keys)
