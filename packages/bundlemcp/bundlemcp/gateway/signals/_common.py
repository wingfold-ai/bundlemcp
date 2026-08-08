"""Shared constants and logger for cross-replica signaling."""

import structlog

log = structlog.get_logger("bundlemcp.gateway.signals")

SIGNAL_PATTERN = "bmcp:signal:*"
