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

    def coerce(self, value: Any) -> bool | int | float:
        """The value as the key's type, or a ValueError naming what was wrong."""
        try:
            return TypeAdapter(self.value_type).validate_python(value, strict=True)
        except ValidationError as exc:
            raise ValueError(
                f"must be {self.value_type.__name__}: {exc.errors()[0]['msg']}"
            ) from None


# The single registry of runtime-tunable settings.
DEFAULTS: dict[str, ConfigSetting] = {
    # PROT-2 timeout model (seconds)
    "call_timeout": ConfigSetting(default=60.0, value_type=float),
    "reset_timeout_on_progress": ConfigSetting(default=True, value_type=bool),
    "max_total_timeout": ConfigSetting(default=1800.0, value_type=float),
    # SES-10 (seconds; 0 = no idle expiry)
    "session_lifetime": ConfigSetting(default=86400, value_type=int),
    # PROT-16 (milliseconds a client may keep a tools/prompts/resources list)
    "list_cache_ttl_ms": ConfigSetting(default=300000, value_type=int),
    # SRV-4
    "server_error_attempts": ConfigSetting(default=3, value_type=int),
    # AUD-5 (days)
    "audit_retention_days": ConfigSetting(default=90, value_type=int),
}


def coerce(key: str, value: Any) -> bool | int | float:
    """Validate a raw (JSON) value against the key's registered type."""
    if key not in DEFAULTS:
        raise UnknownConfigKey(key)
    try:
        return DEFAULTS[key].coerce(value)
    except ValueError as exc:
        raise ValueError(f"{key} {exc}") from None
