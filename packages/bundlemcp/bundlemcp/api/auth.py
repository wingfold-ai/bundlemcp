"""Management-API authentication edge.

Credential resolution is framework-free (``bundlemcp.services.AuthService``);
this module owns the transport concerns the edge decides — the accept-either
401/403 status policy.
"""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from bundlemcp.api.providers import DbProvider
from bundlemcp.models import ApiKeyKind
from bundlemcp.services import AuthService, Principal


def get_auth_service(request: Request, db: DbProvider) -> AuthService:
    return AuthService(db)


AuthServiceProvider = Annotated[AuthService, Depends(get_auth_service)]


class ManagementAuth:
    """Accept a service-kind API key."""

    SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

    async def __call__(self, request: Request, auth: AuthServiceProvider) -> Principal:
        key = await auth.authenticate_api_key(
            authorization=request.headers.get("authorization"),
            x_api_key=request.headers.get("x-api-key"),
        )
        if key is not None and key.kind == ApiKeyKind.SERVICE:
            return Principal(kind="service", api_key_id=str(key.id))
        if key is not None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="key is not service-kind (KEY-2)"
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="service API key required",
        )


ServiceAuthProvider = Annotated[Principal, Depends(ManagementAuth())]
