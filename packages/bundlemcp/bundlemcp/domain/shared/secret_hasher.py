"""One-way hashing of the secrets the gateway stores, behind a contract so the scheme can change."""

from typing import Protocol, runtime_checkable


@runtime_checkable
class SecretHasher(Protocol):
    """Turns a secret into the digest that is stored, and checks a presented secret against one."""

    def digest(self, secret: str) -> str: ...

    def matches(self, secret: str, digest: str) -> bool:
        """Whether the secret hashes to the digest, compared in constant time."""
        ...
