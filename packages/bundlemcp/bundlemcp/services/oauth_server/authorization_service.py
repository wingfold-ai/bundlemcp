"""The authorization endpoint's business logic: validation, consent, code issuance."""

import secrets
from datetime import timedelta

from bundlemcp.crypto import hash_token
from bundlemcp.models import (
    Bundle,
    Endpoint,
    EndpointAuthMode,
    OAuthAuthorizationCode,
    OAuthClient,
    OAuthConsent,
    User,
    utcnow,
)
from bundlemcp.services.errors import AuthorizationRedirectError, InvalidInputError
from bundlemcp.services.oauth_server.authorization_request import AuthorizationRequest
from bundlemcp.services.oauth_server.client_metadata_fetcher import ClientMetadataFetcher
from bundlemcp.services.oauth_server.pending_authorization import PendingAuthorization
from bundlemcp.services.oauth_server.redirect_uri_rule import check_redirect_uri
from bundlemcp.store import Repository, UnitOfWork

CODE_TTL = timedelta(minutes=10)  # OAS-3


class AuthorizationService:
    def __init__(
        self, uow: UnitOfWork, *, public_base: str, client_metadata: ClientMetadataFetcher
    ) -> None:
        self._uow = uow
        self._public_base = public_base
        self._client_metadata = client_metadata
        self._clients = Repository(uow.session, OAuthClient)
        self._endpoints = Repository(uow.session, Endpoint)
        self._bundles = Repository(uow.session, Bundle)
        self._consents = Repository(uow.session, OAuthConsent)
        self._codes = Repository(uow.session, OAuthAuthorizationCode)

    def _endpoint_name_from_resource(self, resource: str) -> str | None:
        """Reverse of the canonical resource identifier; None if it isn't one of ours."""
        base = self._public_base + "/"
        if not resource.startswith(base) or not resource.endswith("/mcp"):
            return None
        name = resource[len(base) : -len("/mcp")]
        return name or None

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

        if request.response_type != "code":
            raise redirect("unsupported_response_type")
        if not request.code_challenge or request.code_challenge_method != "S256":
            raise redirect("invalid_request", "PKCE S256 code_challenge required")
        # OAS-10: resolve the endpoint audience from `resource`
        endpoint_name = self._endpoint_name_from_resource(request.resource)
        if endpoint_name is None:
            raise redirect("invalid_target", "resource must identify a bundlemcp endpoint")
        endpoint = await self._endpoints.by_name(endpoint_name)
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
        if document.client_id != client_id:
            raise InvalidInputError("client metadata document does not name its own URL")
        if document.token_endpoint_auth_method != "none":
            raise InvalidInputError("client metadata documents may only describe public clients")
        for uri in document.redirect_uris:
            check_redirect_uri(uri)
        client = await self._clients.get(client_id)
        if client is None:
            client = OAuthClient(client_id=client_id, token_endpoint_auth_method="none")
        client.client_name = document.client_name
        client.redirect_uris = list(document.redirect_uris)
        client.grant_types = list(document.grant_types)
        client.scope = document.scope or "mcp"
        self._clients.add(client)
        await self._uow.commit()
        return client

    async def has_consent(self, pending: PendingAuthorization) -> bool:
        # OAS-11: persistent consent skips the screen
        consent = await self._consents.one(
            OAuthConsent.user_id == pending.user_id,
            OAuthConsent.client_id == pending.client_id,
            OAuthConsent.endpoint_id == pending.endpoint_id,
            OAuthConsent.revoked_at.is_(None),  # type: ignore[union-attr]
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
                code_challenge_method="S256",
                expires_at=utcnow() + CODE_TTL,
            )
        )
        await self._uow.commit()
        return raw_code
