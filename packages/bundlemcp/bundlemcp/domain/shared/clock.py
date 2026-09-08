"""The one place the current time is read, so a test can pin it."""

from datetime import UTC, datetime


def utcnow() -> datetime:
    return datetime.now(UTC)
