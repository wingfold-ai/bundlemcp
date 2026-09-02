from pydantic import BaseModel, Field, field_validator

from bundlemcp.schemas.validation import validate_name


class BundleUpsert(BaseModel):
    """Body for creating or replacing a bundle."""

    name: str = Field(description="Unique bundle name; lowercase letters, digits and hyphens")
    description: str | None = Field(
        default=None, description="Free-text note about what this bundle is for"
    )

    @field_validator("name")
    @classmethod
    def name_rules(cls, v: str) -> str:
        return validate_name(v)
