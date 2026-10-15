"""Token encryption tests (ARC-18, DEP-9 rotation)."""

import pytest
from bundlemcp.application.contracts.secret_cipher import DecryptionError
from bundlemcp.infrastructure.config.settings import EnvSettings
from bundlemcp.infrastructure.crypto.encryption_not_configured import EncryptionNotConfigured
from bundlemcp.infrastructure.crypto.token_cipher import TokenCipher, token_cipher
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


def test_dep9_an_old_value_is_not_current_and_reencrypts_to_one_that_is():
    """DEP-9: a value under the old key re-encrypts under the new one, same plaintext."""
    old, new = _key(), _key()
    ct = TokenCipher([old]).encrypt("s3cr3t")
    rotated = TokenCipher([new, old])
    assert rotated.is_current(ct) is False
    assert rotated.is_current(rotated.encrypt("fresh")) is True

    reencrypted = rotated.reencrypt(ct)
    assert rotated.is_current(reencrypted) is True
    assert TokenCipher([new]).decrypt(reencrypted) == "s3cr3t"


def test_dep9_an_undecryptable_value_neither_counts_as_current_nor_reencrypts():
    """DEP-9: a value no held key decrypts raises DecryptionError instead of being rewritten."""
    stranger = TokenCipher([_key()]).encrypt("x")
    cipher = TokenCipher([_key(), _key()])
    assert cipher.is_current(stranger) is False
    with pytest.raises(DecryptionError):
        cipher.reencrypt(stranger)


def test_missing_keys_raises():
    with pytest.raises(EncryptionNotConfigured):
        TokenCipher([])
    with pytest.raises(EncryptionNotConfigured):
        token_cipher(EnvSettings(_env_file=None, token_encryption_keys=[]))


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
    cipher = token_cipher(EnvSettings(_env_file=None, token_encryption_keys=[key]))
    assert cipher.decrypt(cipher.encrypt("hi")) == "hi"
