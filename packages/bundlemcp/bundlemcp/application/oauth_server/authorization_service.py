"""The authorization endpoint's use case: validate a request, then consent and a code."""

from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWork
from bundlemcp.application.errors import AuthorizationRedirectError, InvalidInputError
from bundlemcp.application.oauth_server.authorization_code_issuer import AuthorizationCodeIssuer
from bundlemcp.application.oauth_server.authorization_request import AuthorizationRequest
from bundlemcp.application.oauth_server.client_resolver import ClientResolver
from bundlemcp.application.oauth_server.consent_service import ConsentService
from bundlemcp.application.oauth_server.pending_authorization import PendingAuthorization
from bundlemcp.domain.access.user import User
from bundlemcp.domain.endpoints.endpoint_auth_mode import EndpointAuthMode
from bundlemcp.domain.endpoints.endpoint_resource import EndpointResource
from bundlemcp.domain.oauth.code_challenge_method import CodeChallengeMethod
from bundlemcp.domain.oauth.grant_type import GrantType
from bundlemcp.domain.oauth.oauth_error_code import OAuthErrorCode
from bundlemcp.domain.oauth.response_type import ResponseType


class AuthorizationService:
    """Composes client resolution, consent and code issuance behind one door.

    The controller talks to this object only; the three collaborators are
    separately replaceable and separately testable.
    """

    def __init__(
        self,
        uow: UnitOfWork,
        *,
        public_base: str,
        clients: ClientResolver,
        consents: ConsentService,
        codes: AuthorizationCodeIssuer,
    ) -> None:
        self._uow = uow
        self._public_base = public_base
        self._endpoints = uow.endpoints
        self._bundles = uow.bundles
        self._clients = clients
        self._consents = consents
        self._codes = codes

    async def validate(self, request: AuthorizationRequest, user: User) -> PendingAuthorization:
        """Check every parameter and bind the request to the signed-in user.

        Client and redirect problems raise InvalidInputError because nothing may
        be redirected to an unverified URI; everything after that is reported to
        the client through AuthorizationRedirectError.
        """
        client = await self._clients.resolve(request.client_id)
        if client is None:
            raise InvalidInputError("unknown client")
        if request.redirect_uri not in client.redirect_uris:
            raise InvalidInputError("redirect_uri not registered")
        # A client described by a metadata document was mirrored while resolving;
        # persist it now so the code and tokens that follow can bind to it.
        await self._uow.commit()

        def redirect(code: OAuthErrorCode, description: str = "") -> AuthorizationRedirectError:
            return AuthorizationRedirectError(
                request.redirect_uri,
                request.state,
                code,
                description,
                issuer=self._public_base,  # AUTH-14
            )

        if request.response_type != ResponseType.CODE:
            raise redirect(OAuthErrorCode.UNSUPPORTED_RESPONSE_TYPE)
        if not client.allows_grant(GrantType.AUTHORIZATION_CODE):
            raise redirect(OAuthErrorCode.UNAUTHORIZED_CLIENT)
        if not request.code_challenge or request.code_challenge_method != CodeChallengeMethod.S256:
            raise redirect(OAuthErrorCode.INVALID_REQUEST, "PKCE S256 code_challenge required")
        # AUTH-10: resolve the endpoint audience from `resource`
        resource = EndpointResource.parse(self._public_base, request.resource)
        if resource is None:
            raise redirect(
                OAuthErrorCode.INVALID_TARGET, "resource must identify a bundlemcp endpoint"
            )
        endpoint = await self._endpoints.by_name(resource.endpoint_name)
        if endpoint is None or not endpoint.enabled or not endpoint.accepts(EndpointAuthMode.OAUTH):
            raise redirect(OAuthErrorCode.INVALID_TARGET, "unknown endpoint")
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
        """Whether the request names a known client with a registered redirect URI.

        Asked before anyone is signed in, so it commits nothing: a client
        mirrored from a metadata document is written only once a user
        authorizes it.
        """
        try:
            client = await self._clients.resolve(request.client_id)
        except InvalidInputError:
            return False
        return client is not None and request.redirect_uri in client.redirect_uris

    async def has_consent(self, pending: PendingAuthorization) -> bool:
        return await self._consents.is_granted(
            pending.user_id, pending.client_id, pending.endpoint_id
        )

    async def grant_consent(self, pending: PendingAuthorization) -> None:
        await self._consents.grant(pending.user_id, pending.client_id, pending.endpoint_id)

    async def issue_code(self, pending: PendingAuthorization) -> str:
        """Store a single-use authorization code and return its raw value."""
        raw_code = self._codes.issue(pending)
        await self._uow.commit()
        return raw_code
