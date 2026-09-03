"""The key that makes one client invocation chargeable exactly once."""

import uuid


def new_idempotency_key() -> str:
    """A fresh key for one client invocation; internal retries reuse it."""
    return uuid.uuid4().hex
