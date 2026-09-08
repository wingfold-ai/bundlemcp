"""Turning verified identity-provider claims into a local user."""

from collections.abc import Sequence

from pydantic import BaseModel, Field

from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWork
from bundlemcp.domain.access.user import User

ADMIN_GROUP = "bundlemcp-admin"


class VerifiedClaims(BaseModel):
    """The identity facts the provisioning service needs from a login."""

    issuer: str = Field(description="Issuer that authenticated the user")
    sub: str = Field(description="Subject identifier at that issuer")
    email: str | None = Field(default=None, description="Email claim, when sent")
    name: str | None = Field(default=None, description="Display name claim, when sent")
    groups: Sequence[str] = Field(default=(), description="Group claims, when sent")


class UserProvisioningService:
    def __init__(self, uow: UnitOfWork, *, admin_emails: Sequence[str]) -> None:
        self._uow = uow
        self._admin_emails = set(admin_emails)
        self._users = uow.users

    def is_admin(self, claims: VerifiedClaims) -> bool:
        """Admin status is re-evaluated on every login."""
        if claims.email and claims.email in self._admin_emails:
            return True
        return ADMIN_GROUP in claims.groups

    async def provision(self, claims: VerifiedClaims) -> User:
        """Create-or-update by (issuer, sub); refresh is_admin on every login."""
        user = await self._users.by_subject(claims.issuer, claims.sub)
        if user is None:
            user = User(oidc_issuer=claims.issuer, oidc_sub=claims.sub)
        user.email = claims.email
        user.display_name = claims.name
        user.is_admin = self.is_admin(claims)  # ADM-3
        if not user.is_active:
            user.is_active = True  # re-login reactivates unless admin-deactivated separately
        self._users.add(user)
        await self._uow.commit()
        await self._uow.refresh(user)
        return user
