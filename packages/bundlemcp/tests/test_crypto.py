"""Token encryption tests (DOM-3, DEP-9 rotation)."""

import pytest
from bundlemcp.crypto import (
    DecryptionError,
    EncryptionNotConfigured,
    TokenCipher,
    token_cipher,
)
from bundlemcp.settings import Settings
from cryptography.fernet import Fernet


def _key() -> str:
    return Fernet.generate_key().decode()


def test_round_trip():
    cipher = TokenCipher([_key()])
    secret = "refresh-token-abc.123"
    ct = cipher.encrypt(secret)
    assert ct != secret  # actually encrypted
    assert cipher.decrypt(ct) == secret


def test_rotation_first_encrypts_all_decrypt():
    """DEP-9: prepend a new key; old ciphertext still decrypts."""
    old = _key()
    old_cipher = TokenCipher([old])
    ct = old_cipher.encrypt("s3cr3t")

    new = _key()
    rotated = TokenCipher([new, old])  # new first (encrypts), old still decrypts
    assert rotated.decrypt(ct) == "s3cr3t"  # old ciphertext readable

    # a fresh encrypt uses the new primary key
    ct2 = rotated.encrypt("again")
    assert TokenCipher([new]).decrypt(ct2) == "again"

    # rotate() re-encrypts old ciphertext under the primary key
    reencrypted = rotated.rotate(ct)
    assert TokenCipher([new]).decrypt(reencrypted) == "s3cr3t"


def test_missing_keys_raises():
    with pytest.raises(EncryptionNotConfigured):
        TokenCipher([])
    with pytest.raises(EncryptionNotConfigured):
        token_cipher(Settings(_env_file=None, token_encryption_keys=[]))


def test_wrong_key_fails_closed():
    ct = TokenCipher([_key()]).encrypt("x")
    with pytest.raises(DecryptionError):
        TokenCipher([_key()]).decrypt(ct)  # unrelated key


def test_repr_does_not_leak_keys():
    cipher = TokenCipher([_key()])
    assert "redacted" in repr(cipher)
    assert cipher._fernet is not None  # sanity


def test_token_cipher_from_settings():
    key = _key()
    cipher = token_cipher(Settings(_env_file=None, token_encryption_keys=[key]))
    assert cipher.decrypt(cipher.encrypt("hi")) == "hi"
