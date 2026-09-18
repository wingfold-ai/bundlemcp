"""The hashing scheme the gateway stores its own secrets under."""

from bundlemcp.domain.shared.secrets import hash_token, tokens_equal


class Sha256SecretHasher:
    """Plain SHA-256 of the secret: enough for high-entropy tokens the gateway generated itself."""

    def digest(self, secret: str) -> str:
        return hash_token(secret)

    def matches(self, secret: str, digest: str) -> bool:
        return tokens_equal(hash_token(secret), digest)
