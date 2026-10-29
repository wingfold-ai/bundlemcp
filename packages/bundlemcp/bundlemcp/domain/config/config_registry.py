"""The registry of runtime-tunable keys: what exists, and how a value is validated."""

from typing import Any

from annotated_types import Ge, Le
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError
from pydantic.fields import FieldInfo

from bundlemcp.domain.config.runtime_settings import RuntimeSettings
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


def _setting(field: FieldInfo) -> ConfigSetting:
    """The registry entry for one ``RuntimeSettings`` field: its type, default and bounds."""
    return ConfigSetting(
        default=field.default,
        value_type=field.annotation,
        minimum=next((item.ge for item in field.metadata if isinstance(item, Ge)), None),
        maximum=next((item.le for item in field.metadata if isinstance(item, Le)), None),
    )


# The single registry of runtime-tunable settings, one entry per RuntimeSettings field.
DEFAULTS: dict[str, ConfigSetting] = {
    key: _setting(field) for key, field in RuntimeSettings.model_fields.items()
}


def coerce(key: str, value: Any) -> bool | int | float:
    """Validate a raw (JSON) value against the key's registered type."""
    if key not in DEFAULTS:
        raise UnknownConfigKey(key)
    try:
        return DEFAULTS[key].coerce(value)
    except ValueError as exc:
        raise ValueError(f"{key} {exc}") from None
