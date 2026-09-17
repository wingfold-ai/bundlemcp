"""One-way hashing of the secrets the gateway stores, behind a contract so the scheme can change."""

from typing import Protocol, runtime_checkable

from bundlemcp.domain.shared.secrets import hash_token, tokens_equal


@runtime_checkable
class SecretHasher(Protocol):
    """Turns a secret into the digest that is stored, and checks a presented secret against one."""

    def digest(self, secret: str) -> str: ...

    def matches(self, secret: str, digest: str) -> bool:
        """Whether the secret hashes to the digest, compared in constant time."""
        ...


class Sha256SecretHasher:
    """Plain SHA-256 of the secret: enough for high-entropy tokens the gateway generated itself."""

    def digest(self, secret: str) -> str:
        return hash_token(secret)

    def matches(self, secret: str, digest: str) -> bool:
        return tokens_equal(hash_token(secret), digest)
