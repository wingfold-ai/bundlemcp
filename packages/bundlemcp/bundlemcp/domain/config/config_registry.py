"""The registry of runtime-tunable keys: what exists, and how a value is validated."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from bundlemcp.domain.config.unknown_config_key import UnknownConfigKey


class ConfigSetting(BaseModel):
    """One runtime-tunable key: its default and the type a stored value must have."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    default: bool | int | float = Field(description="Value in effect when nothing is stored")
    value_type: type[bool] | type[int] | type[float] = Field(
        description="Type a stored value must already have; nothing is converted, so a "
        "bool is not an int and a string is not a number"
    )
    minimum: int | float | None = Field(
        default=None, description="Smallest value accepted, inclusive; None for no lower bound"
    )
    maximum: int | float | None = Field(
        default=None, description="Largest value accepted, inclusive; None for no upper bound"
    )

    def coerce(self, value: Any) -> bool | int | float:
        """The value as the key's type and within its bounds, or a ValueError saying why not."""
        try:
            coerced = TypeAdapter(self.value_type).validate_python(value, strict=True)
        except ValidationError as exc:
            raise ValueError(
                f"must be {self.value_type.__name__}: {exc.errors()[0]['msg']}"
            ) from None
        if self.minimum is not None and coerced < self.minimum:
            raise ValueError(f"must be at least {self.minimum}")
        if self.maximum is not None and coerced > self.maximum:
            raise ValueError(f"must be at most {self.maximum}")
        return coerced


KIB = 1024
MIB = 1024 * KIB

# The single registry of runtime-tunable settings.
DEFAULTS: dict[str, ConfigSetting] = {
    # per-call timeout model (seconds)
    "call_timeout": ConfigSetting(default=60.0, value_type=float),
    "reset_timeout_on_progress": ConfigSetting(default=True, value_type=bool),
    "max_total_timeout": ConfigSetting(default=1800.0, value_type=float),
    # idle session expiry (seconds; 0 = no idle expiry)
    "session_lifetime": ConfigSetting(default=86400, value_type=int),
    # milliseconds a client may keep a tools/prompts/resources list
    "list_cache_ttl_ms": ConfigSetting(default=300000, value_type=int),
    "server_error_attempts": ConfigSetting(default=3, value_type=int),
    # audit retention (days)
    "audit_retention_days": ConfigSetting(default=90, value_type=int),
    # lifetimes (seconds) of what the gateway's own OAuth server issues
    "authorization_code_lifetime": ConfigSetting(default=600, value_type=int),
    "access_token_lifetime": ConfigSetting(default=3600, value_type=int),
    "refresh_token_lifetime": ConfigSetting(default=604800, value_type=int),
    # bytes: a request body, and one upstream response message
    "max_request_bytes": ConfigSetting(
        default=4 * MIB, value_type=int, minimum=64 * KIB, maximum=64 * MIB
    ),
    "max_upstream_response_bytes": ConfigSetting(
        default=16 * MIB, value_type=int, minimum=64 * KIB, maximum=64 * MIB
    ),
}


def coerce(key: str, value: Any) -> bool | int | float:
    """Validate a raw (JSON) value against the key's registered type."""
    if key not in DEFAULTS:
        raise UnknownConfigKey(key)
    try:
        return DEFAULTS[key].coerce(value)
    except ValueError as exc:
        raise ValueError(f"{key} {exc}") from None
