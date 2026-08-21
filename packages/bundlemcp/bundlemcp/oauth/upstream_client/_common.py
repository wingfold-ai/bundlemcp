"""Shared constants and helpers for upstream OAuth client storage."""

import uuid
from datetime import UTC, datetime, timedelta

import structlog

log = structlog.get_logger("bundlemcp.oauth.upstream_client")

REFRESH_LOCK_KEY = "bmcp:upstream-refresh:{server_id}:{user_key}"
REFRESH_SKEW = timedelta(seconds=60)  # refresh this long before actual expiry
REFRESH_LOCK_TTL = 30  # seconds


def _aware(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def _user_key(user_id: uuid.UUID | None) -> str:
    return str(user_id) if user_id is not None else "shared"
