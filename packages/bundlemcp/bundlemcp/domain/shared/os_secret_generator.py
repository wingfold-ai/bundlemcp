"""Where a running gateway gets the randomness for a new secret."""

import secrets


class OsSecretGenerator:
    """The operating system's randomness."""

    def token(self, nbytes: int) -> str:
        return secrets.token_urlsafe(nbytes)
