"""Encryption-at-rest for upstream OAuth tokens and client secrets.

Uses Fernet (AES-128-CBC + HMAC) via MultiFernet so keys rotate without a
migration: the FIRST configured key encrypts, ALL configured keys can decrypt.
Rotation procedure: prepend a new key, let re-encryption happen lazily
on next write, then drop the old key once nothing decrypts with it.

Keys come from BUNDLEMCP_TOKEN_ENCRYPTION_KEYS (urlsafe-base64 32-byte Fernet
keys). Generate one with `cryptography.fernet.Fernet.generate_key()`.
"""

from bundlemcp.crypto._functions import token_cipher
from bundlemcp.crypto.decryption_error import DecryptionError
from bundlemcp.crypto.encryption_not_configured import EncryptionNotConfigured
from bundlemcp.crypto.token_cipher import TokenCipher

__all__ = [
    "DecryptionError",
    "EncryptionNotConfigured",
    "TokenCipher",
    "token_cipher",
]
