"""The registry of runtime-tunable keys, and the typed settings it is derived from."""

import pytest
from bundlemcp.domain.config.config_registry import DEFAULTS, coerce
from bundlemcp.domain.config.runtime_settings import KIB, MIB

REGISTRY = {
    "call_timeout": (float, 60.0, None, None),
    "reset_timeout_on_progress": (bool, True, None, None),
    "max_total_timeout": (float, 1800.0, None, None),
    "session_lifetime": (int, 86400, 0, None),
    "list_cache_ttl_ms": (int, 300000, None, None),
    "server_error_attempts": (int, 3, 1, None),
    "audit_retention_days": (int, 90, 0, None),
    "authorization_code_lifetime": (int, 600, None, None),
    "access_token_lifetime": (int, 3600, None, None),
    "refresh_token_lifetime": (int, 604800, None, None),
    "max_request_bytes": (int, 4 * MIB, 64 * KIB, 64 * MIB),
    "max_upstream_response_bytes": (int, 16 * MIB, 64 * KIB, 64 * MIB),
    "upstream_sessions_max": (int, 256, 1, None),
    "upstream_sessions_per_server_max": (int, 32, 1, None),
    "upstream_session_idle_timeout": (int, 300, 1, None),
}


def test_ses18_the_registry_keys_defaults_and_bounds() -> None:
    """SES-18: the registry offers exactly these keys, with these types, defaults and bounds."""
    actual = {
        key: (setting.value_type, setting.default, setting.minimum, setting.maximum)
        for key, setting in DEFAULTS.items()
    }

    assert actual == REGISTRY
    for key, (value_type, default, _, _) in REGISTRY.items():
        assert type(DEFAULTS[key].default) is value_type, key
        assert type(default) is value_type, key


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        (
            "max_request_bytes",
            "big",
            "max_request_bytes must be int: Input should be a valid integer",
        ),
        (
            "reset_timeout_on_progress",
            1,
            "reset_timeout_on_progress must be bool: Input should be a valid boolean",
        ),
        (
            "server_error_attempts",
            True,
            "server_error_attempts must be int: Input should be a valid integer",
        ),
        ("max_request_bytes", 64 * KIB - 1, "max_request_bytes must be at least 65536"),
        ("max_request_bytes", 64 * MIB + 1, "max_request_bytes must be at most 67108864"),
        ("session_lifetime", -1, "session_lifetime must be at least 0"),
    ],
)
def test_ses18_rejected_values_keep_their_messages(key: str, value: object, message: str) -> None:
    """SES-18: a value of the wrong type or out of bounds is refused with the same message."""
    with pytest.raises(ValueError) as caught:
        coerce(key, value)

    assert str(caught.value) == message
