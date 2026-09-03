"""Who a request to an MCP endpoint was made by."""

import uuid

from pydantic import BaseModel, ConfigDict, Field

from bundlemcp.models.endpoint_auth_mode import EndpointAuthMode

API_KEY_SUBJECT_PREFIX = "api_key:"  # FWD-3 identity format for key-authenticated callers


class CallerIdentity(BaseModel):
    """The resolved caller of an endpoint: an OAuth user, an API key, or nobody.

    Built once at authentication and carried on the session record, so every
    later step (metering, audit, header forwarding) reads the same answer.
    """

    model_config = ConfigDict(frozen=True)

    auth_method: EndpointAuthMode = Field(description="Which credential authenticated the caller")
    user_id: str | None = Field(default=None, description="Authenticated user, when OAuth was used")
    user_email: str | None = Field(
        default=None, description="Email of the authenticated user, when the issuer supplied one"
    )
    api_key_id: str | None = Field(default=None, description="API key used, when one was")

    @classmethod
    def anonymous(cls) -> "CallerIdentity":
        return cls(auth_method=EndpointAuthMode.NONE)

    @classmethod
    def oauth_user(cls, user_id: uuid.UUID, email: str | None) -> "CallerIdentity":
        return cls(auth_method=EndpointAuthMode.OAUTH, user_id=str(user_id), user_email=email)

    @classmethod
    def with_api_key(cls, key_id: uuid.UUID) -> "CallerIdentity":
        return cls(auth_method=EndpointAuthMode.API_KEY, api_key_id=str(key_id))

    @property
    def sub(self) -> str | None:
        """The subject a call is attributed to: the user, else the key, else nobody."""
        if self.user_id:
            return self.user_id
        if self.api_key_id:
            return f"{API_KEY_SUBJECT_PREFIX}{self.api_key_id}"
        return None

    @property
    def user_uuid(self) -> uuid.UUID | None:
        return uuid.UUID(self.user_id) if self.user_id else None

    @property
    def api_key_uuid(self) -> uuid.UUID | None:
        return uuid.UUID(self.api_key_id) if self.api_key_id else None
