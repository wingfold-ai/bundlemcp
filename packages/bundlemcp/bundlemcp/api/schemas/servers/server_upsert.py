from typing import Literal

from pydantic import BaseModel, Field, field_validator

from bundlemcp.api.schemas.validation import validate_name
from bundlemcp.models import ServerAuthMode


class ServerUpsert(BaseModel):
    """Body for POST /servers and PUT /servers/{name}."""

    name: str
    description: str | None = None
    url: str
    static_headers: dict[str, str] = Field(default_factory=dict)
    forward_headers: dict[str, str] = Field(default_factory=dict)
    auth_mode: ServerAuthMode = ServerAuthMode.NONE
    identity_mode: Literal["shared", "per_user"] = "shared"
    send_identity_header: bool = True
    # API-4: registrar payloads may carry transport; only streamable-http is valid.
    transport: Literal["streamable-http"] | None = None
    force: bool = False  # SRV-5 rename acknowledgement

    @field_validator("name")
    @classmethod
    def name_rules(cls, v: str) -> str:
        validate_name(v)
        if "__" in v:
            raise ValueError("server names must not contain '__' (DOM-4/BND-2)")
        return v

    @field_validator("url")
    @classmethod
    def url_scheme(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("url must be http(s)")
        return v
