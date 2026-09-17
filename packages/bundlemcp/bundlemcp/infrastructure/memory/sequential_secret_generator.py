class SequentialSecretGenerator:
    """Predictable secrets — secret-1, secret-2, … — so a test can name what was issued."""

    def __init__(self, prefix: str = "secret-") -> None:
        self._prefix = prefix
        self._issued = 0

    def token(self, nbytes: int) -> str:
        self._issued += 1
        return f"{self._prefix}{self._issued}"
