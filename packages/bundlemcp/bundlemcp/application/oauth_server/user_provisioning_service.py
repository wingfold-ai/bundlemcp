"""Turning verified identity-provider claims into a local user."""

from collections.abc import Sequence
from typing import Any

import structlog
from pydantic import BaseModel, Field

from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWork
from bundlemcp.domain.access.admin_claim import carries_admin_value
from bundlemcp.domain.access.user import User

log = structlog.get_logger(__name__)


class VerifiedClaims(BaseModel):
    """The identity facts the provisioning service needs from a login."""

    issuer: str = Field(description="Issuer that authenticated the user")
    sub: str = Field(description="Subject identifier at that issuer")
    email: str | None = Field(default=None, description="Email claim, when sent")
    email_verified: bool = Field(
        default=False, description="Whether the issuer vouches for the email; false when unsaid"
    )
    name: str | None = Field(default=None, description="Display name claim, when sent")
    claims: dict[str, Any] = Field(
        default_factory=dict, description="Every claim of the verified token"
    )


class UserProvisioningService:
    def __init__(
        self,
        uow: UnitOfWork,
        *,
        admin_emails: Sequence[str],
        admin_claim: str,
        admin_claim_value: str,
    ) -> None:
        self._uow = uow
        self._admin_emails = set(admin_emails)
        self._admin_claim = admin_claim
        self._admin_claim_value = admin_claim_value
        self._users = uow.users

    def is_admin(self, claims: VerifiedClaims) -> bool:
        """A verified admin email, or the admin claim carrying the admin value.

        Re-evaluated every login. An email counts only when the issuer vouches
        for it: with self-signup or unverified email changes at the identity
        provider, anyone could otherwise claim a listed address.
        """
        listed = claims.email is not None and claims.email in self._admin_emails
        if listed and claims.email_verified:
            return True
        if carries_admin_value(claims.claims, self._admin_claim, self._admin_claim_value):
            return True
        if listed:
            log.warning("user.admin_email_unverified", issuer=claims.issuer)
        return False

    async def provision(self, claims: VerifiedClaims) -> User:
        """Create-or-update by (issuer, sub); refresh is_admin on every login.

        A deactivated user stays deactivated: signing in at the identity
        provider again does not reactivate them, only an administrator does.
        """
        user = await self._users.by_subject(claims.issuer, claims.sub)
        if user is None:
            user = User(oidc_issuer=claims.issuer, oidc_sub=claims.sub)
        user.email = claims.email
        user.display_name = claims.name
        user.is_admin = self.is_admin(claims)
        self._users.add(user)
        await self._uow.commit()
        await self._uow.refresh(user)
        return user
