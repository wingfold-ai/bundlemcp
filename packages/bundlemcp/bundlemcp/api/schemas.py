"""Management-API DTOs (ARC-3): Pydantic models enforcing the domain rules
that table models can't (DOM-4 names, EP-3 auth modes, PROF-6 matrix).
"""

import re
import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from bundlemcp.models import (
    NAME_PATTERN,
    RESERVED_ENDPOINT_NAMES,
    EndpointAuthMode,
    EndpointProfile,
    ServerAuthMode,
)

_name_re = re.compile(NAME_PATTERN)


def _validate_name(value: str) -> str:
    if not _name_re.match(value):
        raise ValueError("name must match ^[a-zA-Z0-9_-]+$")
    return value


# --- Servers (spec 10) -----------------------------------------------------


class ServerUpsert(BaseModel):
    """Body for POST /servers and PUT /servers/{name} (API-4)."""

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
        _validate_name(v)
        if "__" in v:
            raise ValueError("server names must not contain '__' (DOM-4/BND-2)")
        return v

    @field_validator("url")
    @classmethod
    def url_scheme(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("url must be http(s)")
        return v


class ServerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    url: str
    # SRV-3: header VALUES are write-only; only key names leave the API.
    static_header_names: list[str] = []
    forward_headers: dict[str, str]
    auth_mode: str
    identity_mode: str
    send_identity_header: bool
    health_status: str
    last_error: str | None
    created_at: datetime
    updated_at: datetime


# --- Tools (spec 11/13) ----------------------------------------------------


class ToolRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    server_id: uuid.UUID
    name: str
    title: str | None
    description: str | None
    input_schema: dict[str, Any]
    annotations: dict[str, Any] | None
    last_seen_at: datetime


class BundleToolUpdate(BaseModel):
    """Per-bundle curation (TM-1/TM-3/TM-4)."""

    enabled: bool = True
    override_name: str | None = None
    override_title: str | None = None
    override_description: str | None = None
    override_annotations: dict[str, Any] | None = None

    @field_validator("override_name")
    @classmethod
    def override_name_rules(cls, v: str | None) -> str | None:
        if v is not None:
            _validate_name(v)
        return v


# --- Bundles (spec 12) -----------------------------------------------------


class BundleUpsert(BaseModel):
    name: str
    description: str | None = None

    @field_validator("name")
    @classmethod
    def name_rules(cls, v: str) -> str:
        return _validate_name(v)


class BundleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime


class BundleServerUpdate(BaseModel):
    enabled: bool = True


# --- Endpoints (spec 14/15/16) ----------------------------------------------


class RateRule(BaseModel):
    limit: int = Field(gt=0)
    window_seconds: int = Field(gt=0)


class RateLimitConfig(BaseModel):
    """Per-endpoint limits (spec 16, RATE-1/4/6). Stored as JSON on the endpoint."""

    endpoint: RateRule | None = None  # across all callers
    per_client: RateRule | None = None  # per resolved identity (EP-6)
    include_initialize_list: bool = False  # RATE-4: also limit initialize/tools/list
    fail_closed: bool = False  # RATE-6: deny on Redis outage instead of fail-open


class EndpointUpsert(BaseModel):
    name: str
    bundle_name: str
    profile: EndpointProfile = EndpointProfile.DEFAULT
    auth_modes: list[EndpointAuthMode] = Field(default_factory=lambda: [EndpointAuthMode.API_KEY])
    rate_limit: RateLimitConfig | None = None
    enabled: bool = True
    allow_unauthenticated: bool = False  # EP-3: explicit opt-in for `none`
    force: bool = False  # EP-8 rename acknowledgement

    @field_validator("name")
    @classmethod
    def name_rules(cls, v: str) -> str:
        _validate_name(v)
        if v.lower() in RESERVED_ENDPOINT_NAMES:
            raise ValueError(f"'{v}' is a reserved endpoint name (EP-1)")
        return v

    @model_validator(mode="after")
    def auth_and_profile_rules(self) -> "EndpointUpsert":
        modes = set(self.auth_modes)
        if not modes:
            raise ValueError("auth_modes must not be empty (EP-3)")
        if EndpointAuthMode.NONE in modes:
            if modes != {EndpointAuthMode.NONE}:
                raise ValueError("'none' is only valid alone (EP-3)")
            if not self.allow_unauthenticated:
                raise ValueError("'none' requires allow_unauthenticated=true (EP-3)")
        # PROF-6 matrix
        if self.profile == EndpointProfile.CLAUDE and modes != {EndpointAuthMode.OAUTH}:
            raise ValueError("claude profile requires auth_modes == ['oauth'] (PROF-6)")
        if self.profile == EndpointProfile.CHATGPT and not modes & {
            EndpointAuthMode.OAUTH,
            EndpointAuthMode.API_KEY,
        }:
            raise ValueError("chatgpt profile requires oauth or api_key (PROF-6)")
        return self


class EndpointRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    bundle_id: uuid.UUID
    profile: str
    auth_modes: list[str]
    rate_limit: dict[str, Any] | None
    enabled: bool
    created_at: datetime
    updated_at: datetime


# --- API keys (spec 22) ------------------------------------------------------


class ApiKeyCreate(BaseModel):
    name: str
    kind: Literal["endpoint", "service"] = "endpoint"
    endpoint_ids: list[uuid.UUID] = Field(default_factory=list)


class ApiKeyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    key_prefix: str
    kind: str
    endpoint_ids: list[str]
    is_active: bool
    last_used_at: datetime | None
    created_at: datetime


class ApiKeyCreated(ApiKeyRead):
    key: str  # KEY-1: shown exactly once


# --- Pagination (API-5) -------------------------------------------------------


class Page[T](BaseModel):
    items: list[T]
    total: int
    offset: int
    limit: int
