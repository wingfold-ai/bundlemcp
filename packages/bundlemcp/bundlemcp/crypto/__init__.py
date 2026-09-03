"""Cryptographic handling of secrets, both reversible and one-way.

``tokens`` covers one-way handling — generating API keys and bearer tokens,
hashing them for storage, and comparing them in constant time. The rest of this
package is encryption-at-rest for upstream OAuth tokens and client secrets.

Uses Fernet (AES-128-CBC + HMAC) via MultiFernet so keys rotate without a
migration: the FIRST configured key encrypts, ALL configured keys can decrypt.
Rotation procedure: prepend a new key, let re-encryption happen lazily
on next write, then drop the old key once nothing decrypts with it.

Keys come from BUNDLEMCP_TOKEN_ENCRYPTION_KEYS (urlsafe-base64 32-byte Fernet
keys). Generate one with `cryptography.fernet.Fernet.generate_key()`.
"""

from bundlemcp.crypto.decryption_error import DecryptionError
from bundlemcp.crypto.encryption_not_configured import EncryptionNotConfigured
from bundlemcp.crypto.token_cipher import TokenCipher, token_cipher
from bundlemcp.crypto.tokens import (
    ACCESS_TOKEN_PREFIX,
    API_KEY_PREFIX,
    REFRESH_TOKEN_PREFIX,
    display_prefix,
    generate_token,
    hash_token,
    tokens_equal,
)

__all__ = [
    "ACCESS_TOKEN_PREFIX",
    "API_KEY_PREFIX",
    "REFRESH_TOKEN_PREFIX",
    "DecryptionError",
    "EncryptionNotConfigured",
    "TokenCipher",
    "display_prefix",
    "generate_token",
    "hash_token",
    "token_cipher",
    "tokens_equal",
]
