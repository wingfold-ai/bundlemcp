from enum import StrEnum


class CodeChallengeMethod(StrEnum):
    """How a PKCE challenge is derived from its verifier; 'plain' is deliberately absent."""

    S256 = "S256"
