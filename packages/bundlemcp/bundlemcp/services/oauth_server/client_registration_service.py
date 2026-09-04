"""Dynamic client registration (RFC 7591)."""

import secrets
from urllib.parse import urlparse

from bundlemcp.crypto import hash_token
from bundlemcp.models import OAuthClient
from bundlemcp.schemas import ClientRegistrationRequest, ClientRegistrationResponse
from bundlemcp.services.errors import InvalidInputError
from bundlemcp.store import Repository, UnitOfWork


class ClientRegistrationService:
    def __init__(self, uow: UnitOfWork, *, public_base: str) -> None:
        self._uow = uow
        self._public_base = public_base
        self._clients = Repository(uow.session, OAuthClient)

    @staticmethod
    def _check_redirect_uri(uri: str) -> None:
        parsed = urlparse(uri)
        if parsed.scheme == "https" and parsed.hostname:
            return
        if parsed.scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1"):
            return  # native/dev clients
        raise InvalidInputError(f"invalid_redirect_uri: {uri}")

    async def register(self, request: ClientRegistrationRequest) -> ClientRegistrationResponse:
        for uri in request.redirect_uris:
            self._check_redirect_uri(uri)
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
            authorization_endpoint=f"{self._public_base}/oauth/authorize",
            token_endpoint=f"{self._public_base}/oauth/token",
        )
