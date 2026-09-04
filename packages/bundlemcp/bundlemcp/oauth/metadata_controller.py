"""OAuth discovery metadata (RFC 8414 + RFC 9728)."""

from fastapi import HTTPException

from bundlemcp.http import Controller, route
from bundlemcp.oauth.urls import endpoint_resource
from bundlemcp.providers import EndpointServiceProvider, SettingsProvider
from bundlemcp.schemas import AuthorizationServerMetadata, ProtectedResourceMetadata
from bundlemcp.services.errors import NotFoundError


class OAuthMetadataController(Controller):
    prefix = "/.well-known"
    tags = ("oauth",)
    include_in_schema = False

    @route.get("/oauth-authorization-server")
    async def authorization_server(self, settings: SettingsProvider) -> AuthorizationServerMetadata:
        return AuthorizationServerMetadata.for_issuer(settings.public_base)

    @route.get("/oauth-protected-resource/{endpoint_name}/mcp")
    async def protected_resource(
        self, endpoint_name: str, endpoints: EndpointServiceProvider, settings: SettingsProvider
    ) -> ProtectedResourceMetadata:
        """RFC 9728, per endpoint — the 401 challenge points here."""
        try:
            endpoint = await endpoints.get(endpoint_name)
        except NotFoundError:
            raise HTTPException(404, "unknown resource") from None
        if not endpoint.enabled:
            raise HTTPException(404, "unknown resource")
        return ProtectedResourceMetadata(
            resource=endpoint_resource(settings, endpoint_name),
            authorization_servers=[settings.public_base],
        )
