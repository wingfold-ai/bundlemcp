from typing import Self

from pydantic import BaseModel, ConfigDict


class EntityRead(BaseModel):
    """A read DTO built from a stored entity.

    Subclasses whose fields mirror the entity inherit the default; one whose
    shape differs (withheld secrets, derived columns) overrides ``from_entity``.
    """

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_entity(cls, entity: object) -> Self:
        return cls.model_validate(entity)
