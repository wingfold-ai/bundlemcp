"""Dynamic client registration (RFC 7591)."""

from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWork
from bundlemcp.application.errors import OAuthError
from bundlemcp.application.schemas import ClientRegistrationRequest, ClientRegistrationResponse
from bundlemcp.domain.oauth.oauth_client import OAuthClient
from bundlemcp.domain.oauth.oauth_error_code import OAuthErrorCode
from bundlemcp.domain.oauth.redirect_uri_rule import InvalidRedirectUri, check_redirect_uri
from bundlemcp.domain.oauth.token_endpoint_auth_method import TokenEndpointAuthMethod
from bundlemcp.domain.shared.secret_generator import SecretGenerator
from bundlemcp.domain.shared.secret_hasher import SecretHasher


class ClientRegistrationService:
    def __init__(
        self,
        uow: UnitOfWork,
        *,
        public_base: str,
        generator: SecretGenerator,
        hasher: SecretHasher,
    ) -> None:
        self._uow = uow
        self._public_base = public_base
        self._generator = generator
        self._hasher = hasher
        self._clients = uow.oauth_clients

    async def register(self, request: ClientRegistrationRequest) -> ClientRegistrationResponse:
        for uri in request.redirect_uris:
            try:
                check_redirect_uri(uri)
            except InvalidRedirectUri:
                # RFC 7591 section 3.2.2: the protocol's error code, not a generic 4xx
                raise OAuthError(
                    OAuthErrorCode.INVALID_REDIRECT_URI,
                    f"{uri} must be https, or http on localhost",
                ) from None
        client_id = f"bmcp_client_{self._generator.token(16)}"
        client_secret: str | None = None
        if request.token_endpoint_auth_method != TokenEndpointAuthMethod.NONE:
            client_secret = self._generator.token(32)
        self._clients.add(
            OAuthClient(
                client_id=client_id,
                client_secret_hash=self._hasher.digest(client_secret) if client_secret else None,
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
