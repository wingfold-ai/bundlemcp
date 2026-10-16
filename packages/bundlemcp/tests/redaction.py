"""Asserting that text a client or an operator can read carries none of the given secrets."""


def assert_redacted(text: str, secrets: list[str]) -> None:
    """Fail naming the first secret found in ``text``; empty secrets are ignored."""
    for secret in secrets:
        if secret and secret in text:
            raise AssertionError(f"a secret appears in the text: {secret[:6]}…")
