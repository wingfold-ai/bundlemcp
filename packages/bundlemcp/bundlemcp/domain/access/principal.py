from pydantic import BaseModel, ConfigDict, Field

from bundlemcp.domain.access.principal_kind import PrincipalKind


class Principal(BaseModel):
    """The authenticated management-API caller: an admin user or a service key."""

    model_config = ConfigDict(frozen=True)

    kind: PrincipalKind = Field(description="Which credential authenticated the call")
    user_id: str | None = Field(
        default=None, description="Admin user behind the session; None for service keys"
    )
    api_key_id: str | None = Field(
        default=None, description="Service key used; None for admin sessions"
    )

    @property
    def caller_key(self) -> str:
        """A stable name for the caller, safe to log: the user or key id, never a credential."""
        if self.api_key_id is not None:
            return f"api_key:{self.api_key_id}"
        return f"user:{self.user_id}"
