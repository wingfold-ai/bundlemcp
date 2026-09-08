"""Dynamic client registration (RFC 7591)."""

import secrets

from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWork
from bundlemcp.application.errors import InvalidInputError
from bundlemcp.application.schemas import ClientRegistrationRequest, ClientRegistrationResponse
from bundlemcp.domain.oauth.oauth_client import OAuthClient
from bundlemcp.domain.oauth.redirect_uri_rule import InvalidRedirectUri, check_redirect_uri
from bundlemcp.domain.shared.secrets import hash_token


class ClientRegistrationService:
    def __init__(self, uow: UnitOfWork, *, public_base: str) -> None:
        self._uow = uow
        self._public_base = public_base
        self._clients = uow.oauth_clients

    async def register(self, request: ClientRegistrationRequest) -> ClientRegistrationResponse:
        for uri in request.redirect_uris:
            try:
                check_redirect_uri(uri)
            except InvalidRedirectUri as exc:
                raise InvalidInputError(str(exc)) from None
        client_id = f"bmcp_client_{secrets.token_urlsafe(16)}"
        client_secret: str | None = None
        if request.token_endpoint_auth_method != "none":
            client_secret = secrets.token_urlsafe(32)
        self._clients.add(
            OAuthClient(
                client_id=client_id,
                client_secret_hash=hash_token(client_secret) if client_secret else None,
                client_name=request.client_name,
                redirect_uris=request.redirect_uris,
                grant_types=request.grant_types,
                token_endpoint_auth_method=request.token_endpoint_auth_method,
                scope=request.scope,
                application_type=request.application_type,
            )
        )
        await self._uow.commit()
        return ClientRegistrationResponse(
            client_id=client_id,
            client_secret=client_secret,  # shown once (DOM-3)
            client_name=request.client_name,
            redirect_uris=request.redirect_uris,
            grant_types=request.grant_types,
            response_types=request.response_types,
            token_endpoint_auth_method=request.token_endpoint_auth_method,
            scope=request.scope,
            application_type=request.application_type,
            authorization_endpoint=f"{self._public_base}/oauth/authorize",
            token_endpoint=f"{self._public_base}/oauth/token",
        )
