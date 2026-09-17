"""The authorization endpoint's business logic: validation, consent, code issuance."""

import secrets
from datetime import timedelta

from bundlemcp.application.contracts.identity.client_metadata_fetcher import ClientMetadataFetcher
from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWork
from bundlemcp.application.errors import AuthorizationRedirectError, InvalidInputError
from bundlemcp.application.oauth_server.authorization_request import AuthorizationRequest
from bundlemcp.application.oauth_server.pending_authorization import PendingAuthorization
from bundlemcp.domain.access.user import User
from bundlemcp.domain.endpoints.endpoint_auth_mode import EndpointAuthMode
from bundlemcp.domain.endpoints.endpoint_resource import EndpointResource
from bundlemcp.domain.oauth.client_id_metadata_document import InvalidClientMetadataDocument
from bundlemcp.domain.oauth.code_challenge_method import CodeChallengeMethod
from bundlemcp.domain.oauth.grant_type import GrantType
from bundlemcp.domain.oauth.oauth_authorization_code import OAuthAuthorizationCode
from bundlemcp.domain.oauth.oauth_client import OAuthClient
from bundlemcp.domain.oauth.oauth_consent import OAuthConsent
from bundlemcp.domain.oauth.response_type import ResponseType
from bundlemcp.domain.oauth.token_endpoint_auth_method import TokenEndpointAuthMethod
from bundlemcp.domain.shared.clock import utcnow
from bundlemcp.domain.shared.secrets import hash_token

CODE_TTL = timedelta(minutes=10)  # OAS-3


class AuthorizationService:
    def __init__(
        self, uow: UnitOfWork, *, public_base: str, client_metadata: ClientMetadataFetcher
    ) -> None:
        self._uow = uow
        self._public_base = public_base
        self._client_metadata = client_metadata
        self._clients = uow.oauth_clients
        self._endpoints = uow.endpoints
        self._bundles = uow.bundles
        self._consents = uow.consents
        self._codes = uow.authorization_codes

    async def validate(self, request: AuthorizationRequest, user: User) -> PendingAuthorization:
        """Check every parameter and bind the request to the signed-in user.

        Client and redirect problems raise InvalidInputError because nothing may
        be redirected to an unverified URI; everything after that is reported to
        the client through AuthorizationRedirectError.
        """
        client = await self._resolve_client(request.client_id)
        if client is None:
            raise InvalidInputError("unknown client")
        if request.redirect_uri not in client.redirect_uris:
            raise InvalidInputError("redirect_uri not registered")

        def redirect(error: str, description: str = "") -> AuthorizationRedirectError:
            return AuthorizationRedirectError(
                request.redirect_uri,
                request.state,
                error,
                description,
                issuer=self._public_base,  # OAS-14
            )

        if request.response_type != ResponseType.CODE:
            raise redirect("unsupported_response_type")
        if not client.allows_grant(GrantType.AUTHORIZATION_CODE):
            raise redirect("unauthorized_client")
        if not request.code_challenge or request.code_challenge_method != CodeChallengeMethod.S256:
            raise redirect("invalid_request", "PKCE S256 code_challenge required")
        # OAS-10: resolve the endpoint audience from `resource`
        resource = EndpointResource.parse(self._public_base, request.resource)
        if resource is None:
            raise redirect("invalid_target", "resource must identify a bundlemcp endpoint")
        endpoint = await self._endpoints.by_name(resource.endpoint_name)
        if endpoint is None or not endpoint.enabled or not endpoint.accepts(EndpointAuthMode.OAUTH):
            raise redirect("invalid_target", "unknown endpoint")
        bundle = await self._bundles.get(endpoint.bundle_id)
        return PendingAuthorization(
            client_id=client.client_id,
            client_name=client.client_name or client.client_id,
            redirect_uri=request.redirect_uri,
            state=request.state,
            scope=request.scope or client.scope,
            code_challenge=request.code_challenge,
            endpoint_id=endpoint.id,
            endpoint_name=endpoint.name,
            bundle_name=bundle.name if bundle else "",
            user_id=user.id,
        )

    async def client_is_registered(self, request: AuthorizationRequest) -> bool:
        """Whether the request names a known client with a registered redirect URI."""
        try:
            client = await self._resolve_client(request.client_id)
        except InvalidInputError:
            return False
        return client is not None and request.redirect_uri in client.redirect_uris

    async def _resolve_client(self, client_id: str) -> OAuthClient | None:
        """The registered client, or the one a metadata document describes.

        A client whose id is an https URL needs no registration: its document
        is fetched, checked, and mirrored into the client table so codes, tokens
        and consent bind to it like any other client. The mirror is refreshed on
        every authorization, so a changed document takes effect at once.
        """
        if not client_id.startswith("https://"):
            return await self._clients.get(client_id)
        # OAS-13
        document = await self._client_metadata.fetch(client_id)
        try:
            document.check(fetched_from=client_id)
        except InvalidClientMetadataDocument as exc:
            raise InvalidInputError(str(exc)) from None
        client = await self._clients.get(client_id)
        if client is None:
            client = OAuthClient(
                client_id=client_id, token_endpoint_auth_method=TokenEndpointAuthMethod.NONE
            )
        client.apply_metadata_document(document)
        self._clients.add(client)
        await self._uow.commit()
        return client

    async def has_consent(self, pending: PendingAuthorization) -> bool:
        # OAS-11: persistent consent skips the screen
        consent = await self._consents.active(
            pending.user_id, pending.client_id, pending.endpoint_id
        )
        return consent is not None

    async def grant_consent(self, pending: PendingAuthorization) -> None:
        self._consents.add(
            OAuthConsent(
                user_id=pending.user_id,
                client_id=pending.client_id,
                endpoint_id=pending.endpoint_id,
            )
        )
        await self._uow.commit()

    async def issue_code(self, pending: PendingAuthorization) -> str:
        """Store a single-use authorization code and return its raw value."""
        raw_code = secrets.token_urlsafe(32)
        self._codes.add(
            OAuthAuthorizationCode(
                code_hash=hash_token(raw_code),
                client_id=pending.client_id,
                user_id=pending.user_id,
                endpoint_id=pending.endpoint_id,
                redirect_uri=pending.redirect_uri,
                scope=pending.scope,
                code_challenge=pending.code_challenge,
                code_challenge_method=CodeChallengeMethod.S256,
                expires_at=utcnow() + CODE_TTL,
            )
        )
        await self._uow.commit()
        return raw_code
