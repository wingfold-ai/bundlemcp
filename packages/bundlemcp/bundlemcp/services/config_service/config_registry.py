"""The registry of runtime-tunable keys: what exists, and how a value is validated."""

from typing import Any

from bundlemcp.services.config_service.unknown_config_key import UnknownConfigKey

# key -> (default, type). The single registry of runtime-tunable settings.
DEFAULTS: dict[str, tuple[Any, type]] = {
    # PROT-2 timeout model (seconds)
    "call_timeout": (60.0, float),
    "reset_timeout_on_progress": (True, bool),
    "max_total_timeout": (1800.0, float),
    # SES-10 (seconds; 0 = no idle expiry)
    "session_lifetime": (86400, int),
    # PROT-16 (milliseconds a client may keep a tools/prompts/resources list)
    "list_cache_ttl_ms": (300000, int),
    # SRV-4
    "server_error_attempts": (3, int),
    # AUD-5 (days)
    "audit_retention_days": (90, int),
}


def coerce(key: str, value: Any) -> Any:
    """Validate/coerce a raw (JSON) value against the key's registered type."""
    if key not in DEFAULTS:
        raise UnknownConfigKey(key)
    default, typ = DEFAULTS[key]
    if typ is bool:
        if isinstance(value, bool):
            return value
        raise ValueError(f"{key} must be a boolean")
    if typ is float:
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ValueError(f"{key} must be a number")
        return float(value)
    if typ is int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{key} must be an integer")
        return value
    return value
