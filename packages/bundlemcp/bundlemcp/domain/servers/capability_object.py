from typing import Any, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    ModelWrapValidatorHandler,
    PrivateAttr,
    SerializerFunctionWrapHandler,
    model_serializer,
    model_validator,
)


class CapabilityObject(BaseModel):
    """An object from an MCP capabilities snapshot, typed where the gateway reads it.

    Keys the gateway does not read are kept as they came. Serialised, the
    object is the snapshot it was read from: the same keys, in the same
    order, under their wire names, and without the typed members it lacked.
    """

    model_config = ConfigDict(
        frozen=True, extra="allow", validate_by_name=True, serialize_by_alias=True
    )

    # Wire keys in the order they were read; empty for an object built in code.
    _key_order: tuple[str, ...] = PrivateAttr(default=())

    @model_validator(mode="wrap")
    @classmethod
    def _remember_key_order(cls, data: Any, handler: ModelWrapValidatorHandler[Self]) -> Self:
        snapshot = handler(data)
        if isinstance(data, dict):
            wire_names = {name: field.alias or name for name, field in cls.model_fields.items()}
            snapshot._key_order = tuple(wire_names.get(key, key) for key in data)
        return snapshot

    @model_serializer(mode="wrap")
    def _as_advertised(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        absent = {
            field.alias or name
            for name, field in type(self).model_fields.items()
            if getattr(self, name) is None
        }
        advertised = {key: value for key, value in handler(self).items() if key not in absent}
        if not advertised.keys() <= set(self._key_order):
            return advertised  # built or changed in code: declaration order, then the rest
        return {key: advertised[key] for key in self._key_order if key in advertised}

    def __eq__(self, other: object) -> bool:
        """Two objects are equal when they advertise the same, whatever their key order."""
        if not isinstance(other, CapabilityObject):
            return NotImplemented
        return type(self) is type(other) and self.model_dump() == other.model_dump()

    __hash__ = None  # type: ignore[assignment]
