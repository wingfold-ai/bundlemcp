"""Proof Key for Code Exchange (RFC 7636), S256 method only."""

import base64
import hashlib
import hmac
import secrets

from pydantic import BaseModel, ConfigDict, Field


def pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def pkce_verifies(verifier: str, challenge: str) -> bool:
    return hmac.compare_digest(pkce_challenge(verifier), challenge)


class PkcePair(BaseModel):
    """A verifier and the challenge derived from it, for a flow this gateway initiates."""

    model_config = ConfigDict(frozen=True)

    verifier: str = Field(repr=False, description="Secret kept until the token exchange")
    challenge: str = Field(description="S256 digest sent with the authorization request")

    @classmethod
    def generate(cls) -> PkcePair:
        verifier = secrets.token_urlsafe(48)
        return cls(verifier=verifier, challenge=pkce_challenge(verifier))
