from pydantic import BaseModel, ConfigDict, Field

from bundlemcp.domain.access.caller_identity import CallerIdentity


class AuthenticationOutcome(BaseModel):
    """What one request's credential proved on one endpoint.

    ``identity`` is set when it authenticates the caller here. ``forbidden`` is
    set when the credential is valid but not entitled to this endpoint (an API
    key scoped elsewhere, an access token issued for another endpoint), so the
    attempt can be audited; such a request is refused like any other.
    """

    model_config = ConfigDict(frozen=True)

    identity: CallerIdentity | None = Field(
        default=None, description="The authenticated caller; None when nothing authenticated"
    )
    forbidden: CallerIdentity | None = Field(
        default=None, description="Who holds a valid credential this endpoint does not accept"
    )

    @classmethod
    def authenticated(cls, identity: CallerIdentity) -> AuthenticationOutcome:
        return cls(identity=identity)

    @classmethod
    def not_entitled(cls, holder: CallerIdentity) -> AuthenticationOutcome:
        return cls(forbidden=holder)

    @classmethod
    def nobody(cls) -> AuthenticationOutcome:
        return cls()
