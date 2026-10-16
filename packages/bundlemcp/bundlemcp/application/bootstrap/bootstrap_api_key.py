from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from bundlemcp.domain.access.api_key_kind import ApiKeyKind


class BootstrapApiKey(BaseModel):
    """An API key the document provisions, without ever holding its value.

    The value comes from an environment variable the entry names, or is
    generated on first boot and written to a file the entry names. A key whose
    name already exists is left exactly as it is.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        min_length=1, description="Name of the key; it is matched to a stored key by this"
    )
    kind: ApiKeyKind = Field(
        default=ApiKeyKind.ENDPOINT,
        description="'endpoint' keys call MCP endpoints; 'service' keys call the management API",
    )
    endpoints: list[str] = Field(
        default=[],
        description="Names of the endpoints an endpoint-kind key may call; empty means every "
        "endpoint. Each must be defined by the document or already stored",
    )
    value_from_env: str | None = Field(
        default=None,
        pattern=r"^[A-Za-z_][A-Za-z0-9_]*$",
        description="Environment variable holding the key's value, a bmcp_sk_ token supplied "
        "out of band; the document never carries a value itself",
    )
    create_if_missing: bool = Field(
        default=False,
        description="Generate the value on first boot and write it to 'write_to' instead of "
        "reading it from a variable",
    )
    write_to: str | None = Field(
        default=None,
        min_length=1,
        description="File a generated value is written to, created with mode 0600 and never "
        "overwritten; a file that already holds a value supplies it instead",
    )

    @model_validator(mode="after")
    def _one_source(self) -> Self:
        if (self.value_from_env is not None) == self.create_if_missing:
            raise ValueError(
                f"api key {self.name!r} needs exactly one of value_from_env or create_if_missing"
            )
        if self.create_if_missing != (self.write_to is not None):
            raise ValueError(f"api key {self.name!r}: write_to goes with create_if_missing, only")
        if self.kind is ApiKeyKind.SERVICE and self.endpoints:
            raise ValueError(f"api key {self.name!r}: a service key has no endpoint scope")
        return self
