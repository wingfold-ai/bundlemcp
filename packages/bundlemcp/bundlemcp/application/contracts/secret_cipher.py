from typing import Protocol, runtime_checkable


@runtime_checkable
class SecretCipher(Protocol):
    """Reversible encryption for secrets the gateway must hand back out, such as upstream tokens."""

    def encrypt(self, plaintext: str) -> str:
        """The ciphertext for storage; opaque, safe to persist."""
        ...

    def decrypt(self, ciphertext: str) -> str:
        """The plaintext back; raises when the ciphertext was not produced by a known key."""
        ...

    def is_current(self, ciphertext: str) -> bool:
        """Whether the value is encrypted under the primary key, the one new values use."""
        ...

    def reencrypt(self, ciphertext: str) -> str:
        """The same plaintext encrypted under the primary key; raises DecryptionError when no
        held key decrypts the value."""
        ...


class DecryptionError(Exception):
    """The ciphertext was not produced by any key the cipher holds, or was altered."""
