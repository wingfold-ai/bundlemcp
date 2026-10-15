"""The ``resource`` a token request names (RFC 8707), checked against the grant's audience."""

import uuid

from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWork
from bundlemcp.application.errors import OAuthError
from bundlemcp.application.oauth_server.token_request import TokenRequest
from bundlemcp.domain.oauth.oauth_error_code import OAuthErrorCode


async def ensure_resource_is_the_audience(
    uow: UnitOfWork, request: TokenRequest, audience: uuid.UUID
) -> None:
    """Refuse with invalid_target unless an omitted or named resource is the grant's own endpoint.

    Without ``resource`` the issued tokens inherit the grant's audience. With
    one, it must name exactly that endpoint; anything else issues nothing, and
    the caller checks this before a code is burnt or a refresh token rotated.
    """
    if request.resource is None:
        return
    endpoint = (
        await uow.endpoints.by_name(request.resource_endpoint)
        if request.resource_endpoint is not None
        else None
    )
    if endpoint is None or endpoint.id != audience:
        raise OAuthError(
            OAuthErrorCode.INVALID_TARGET,
            "resource must name the endpoint the grant was issued for",
        )
