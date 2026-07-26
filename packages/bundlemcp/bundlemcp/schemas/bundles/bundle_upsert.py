from pydantic import BaseModel, field_validator

from bundlemcp.schemas.validation import validate_name


class BundleUpsert(BaseModel):
    name: str
    description: str | None = None

    @field_validator("name")
    @classmethod
    def name_rules(cls, v: str) -> str:
        return validate_name(v)
