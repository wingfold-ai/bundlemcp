from typing import Any, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
    model_validator,
)

from bundlemcp.domain.upstream_oauth.client_identification import ClientIdentification
from bundlemcp.domain.upstream_oauth.upstream_grant import UpstreamGrant
from bundlemcp.domain.upstream_oauth.upstream_metadata import UpstreamMetadata

# Keys of the stored record that belong to the gateway rather than the authorization server.
GATEWAY_KEYS = ("identification", "grant_type", "step_up_scopes")
# Keys of the stored record that describe the authorization server.
ENDPOINT_KEYS = frozenset(UpstreamMetadata.model_fields) - {"step_up_scopes"}
# The endpoints that must both be known before the remembered ones are used.
REQUIRED_ENDPOINT_KEYS = ("authorization_endpoint", "token_endpoint")


class UpstreamClientMetadata(BaseModel):
    """What the gateway remembers about its client at one upstream authorization server.

    Stored as one flat object: the authorization server's endpoints beside how
    the client was obtained, its grant and the scopes the upstream later
    demanded. A key absent from the record means its default and is written
    back absent, so a record reads and writes as it was stored. Keys the
    gateway does not know are kept as they came.
    """

    model_config = ConfigDict(frozen=True, extra="allow", validate_by_name=True)

    identification: ClientIdentification = Field(
        default=ClientIdentification.PREREGISTERED,
        description="How the client was obtained; a record without one was stored by an admin",
    )
    grant: UpstreamGrant = Field(
        default=UpstreamGrant.AUTHORIZATION_CODE,
        alias="grant_type",
        description="How the gateway obtains tokens with this client",
    )
    step_up_scopes: tuple[str, ...] = Field(
        default=(),
        description="Scopes an upstream demanded with insufficient_scope, in the order demanded",
    )
    endpoints: UpstreamMetadata | None = Field(
        default=None,
        description="The authorization server's endpoints as configured or discovered; None "
        "unless both the authorization and the token endpoint are known",
    )

    @model_validator(mode="before")
    @classmethod
    def _split_stored_record(cls, data: Any) -> Any:
        if not isinstance(data, dict) or "endpoints" in data:
            return data
        record = dict(data)
        gateway = {key: record.pop(key) for key in GATEWAY_KEYS if key in record}
        if not all(record.get(key) for key in REQUIRED_ENDPOINT_KEYS):
            return {**gateway, **record}
        endpoints = {key: record.pop(key) for key in list(record) if key in ENDPOINT_KEYS}
        return {**gateway, "endpoints": endpoints, **record}

    @model_serializer(mode="wrap")
    def _as_stored_record(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        record: dict[str, Any] = {}
        if self.endpoints is not None:
            record |= self.endpoints.model_dump(
                mode="json", exclude_unset=True, exclude={"step_up_scopes"}
            )
        if "identification" in self.model_fields_set:
            record["identification"] = self.identification.value
        if "grant" in self.model_fields_set:
            record["grant_type"] = self.grant.value
        if "step_up_scopes" in self.model_fields_set:
            record["step_up_scopes"] = list(self.step_up_scopes)
        return record | (self.model_extra or {})

    @classmethod
    def obtained(cls, meta: UpstreamMetadata, identification: ClientIdentification) -> Self:
        """The record of a client the gateway obtained itself, for these endpoints."""
        stored = meta.model_dump(exclude_none=True, exclude={"step_up_scopes"})
        return cls(identification=identification, endpoints=UpstreamMetadata(**stored))

    def configured_by_admin(
        self, grant: UpstreamGrant, authorization_url: str | None, token_url: str | None
    ) -> Self:
        """This record once an admin stores a client: preregistered, with this grant.

        The two URLs replace the remembered endpoints only when both are given;
        everything else remembered is kept.
        """
        record = self.model_dump()
        if authorization_url and token_url:
            record |= {"authorization_endpoint": authorization_url, "token_endpoint": token_url}
        record |= {
            "identification": ClientIdentification.PREREGISTERED.value,
            "grant_type": grant.value,
        }
        return type(self).model_validate(record)

    def with_step_up(self, scopes: list[str]) -> Self:
        """This record with the demanded scopes added once each, after those already known."""
        merged = tuple(dict.fromkeys([*self.step_up_scopes, *scopes]))
        if merged == self.step_up_scopes:
            return self
        return self.model_copy(update={"step_up_scopes": merged})

    @property
    def remembered_endpoints(self) -> UpstreamMetadata | None:
        """The endpoints to connect with, carrying the step-up scopes; None to discover them."""
        if self.endpoints is None:
            return None
        return self.endpoints.model_copy(update={"step_up_scopes": list(self.step_up_scopes)})

    @property
    def is_admin_stored(self) -> bool:
        """An admin entered it; the gateway never discards or replaces it on its own."""
        return self.identification == ClientIdentification.PREREGISTERED
