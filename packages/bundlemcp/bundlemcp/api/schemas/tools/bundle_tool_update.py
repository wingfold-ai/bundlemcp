from typing import Any

from pydantic import BaseModel, field_validator

from bundlemcp.api.schemas.validation import validate_name


class BundleToolUpdate(BaseModel):
    """Per-bundle tool curation: enable/disable plus name/metadata overrides."""

    enabled: bool = True
    override_name: str | None = None
    override_title: str | None = None
    override_description: str | None = None
    override_annotations: dict[str, Any] | None = None

    @field_validator("override_name")
    @classmethod
    def override_name_rules(cls, v: str | None) -> str | None:
        if v is not None:
            validate_name(v)
        return v
