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


class DecryptionError(Exception):
    """The ciphertext was not produced by any key the cipher holds, or was altered."""
