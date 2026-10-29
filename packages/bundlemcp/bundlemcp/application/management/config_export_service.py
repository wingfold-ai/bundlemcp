"""Writing the whole configuration out as a document bootstrap and import both accept."""

import uuid

from bundlemcp.application.bootstrap.bootstrap_bundle import BootstrapBundle
from bundlemcp.application.bootstrap.bootstrap_member import BootstrapCuration, BootstrapMember
from bundlemcp.application.bootstrap.bootstrap_oauth_client import BootstrapOAuthClient
from bundlemcp.application.bootstrap.bootstrap_server import BootstrapServer
from bundlemcp.application.bootstrap.export_document import ExportDocument
from bundlemcp.application.bootstrap.secret_ref import SecretRef
from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWork
from bundlemcp.application.contracts.secret_cipher import SecretCipher
from bundlemcp.application.schemas import (
    BundlePromptUpsert,
    BundleResourceUpsert,
    EndpointUpsert,
)
from bundlemcp.domain.access.principal import Principal
from bundlemcp.domain.audit.audit_record import AuditRecord
from bundlemcp.domain.bundles.bundle import Bundle
from bundlemcp.domain.endpoints.endpoint import Endpoint
from bundlemcp.domain.endpoints.endpoint_auth_mode import EndpointAuthMode
from bundlemcp.domain.servers.mcp_server import McpServer

CREDENTIALS_WARNING = (
    "This document contains credentials: upstream header values and OAuth client secrets. "
    "Store and send it as you would a password."
)
CLIENT_SECRET = "client_secret"
EVERYTHING = 10_000  # no gateway holds anywhere near this many of one resource
SECRETS_EXPORTED = "export.secrets_included"


class ConfigExportService:
    """The configuration as a document, every resource by its natural key.

    Upstreams, bundles with their members, curation, prompts and resources, and
    endpoints; never users, OAuth server state, API keys, audit records or the
    upstream tokens users connected. Secrets become named placeholders unless
    ``include_secrets`` asks for the values, and then the document says so in its
    ``warning``, and an audit record names who took it. A client the gateway
    registered for itself is not exported: the target registers its own.
    """

    def __init__(self, uow: UnitOfWork, *, cipher: SecretCipher | None) -> None:
        # cipher is None exactly when no token encryption keys are configured
        self._uow = uow
        self._cipher = cipher

    async def export(self, *, include_secrets: bool, requested_by: Principal) -> ExportDocument:
        """The document; with ``include_secrets`` the values, recorded against ``requested_by``."""
        if include_secrets:
            self._uow.audit_records.add(
                AuditRecord.management_event(
                    SECRETS_EXPORTED,
                    user_id=uuid.UUID(requested_by.user_id) if requested_by.user_id else None,
                    api_key_id=(
                        uuid.UUID(requested_by.api_key_id) if requested_by.api_key_id else None
                    ),
                    auth_method=None,
                )
            )
            await self._uow.commit()
        servers = (await self._uow.servers.page(offset=0, limit=EVERYTHING)).items
        bundles = (await self._uow.bundles.page(offset=0, limit=EVERYTHING)).items
        endpoints = (await self._uow.endpoints.page(offset=0, limit=EVERYTHING)).items
        names = {server.id: server.name for server in servers}
        bundle_names = {bundle.id: bundle.name for bundle in bundles}
        return ExportDocument(
            upstreams=[await self._server(server, include_secrets) for server in servers],
            bundles=[await self._bundle(bundle, names) for bundle in bundles],
            endpoints=[self._endpoint(endpoint, bundle_names) for endpoint in endpoints],
            warning=CREDENTIALS_WARNING if include_secrets else None,
        )

    async def _server(self, server: McpServer, include_secrets: bool) -> BootstrapServer:
        headers: dict[str, str | SecretRef] = {
            name: value if include_secrets else SecretRef(name=name)
            for name, value in server.static_headers.items()
        }
        return BootstrapServer(
            name=server.name,
            description=server.description,
            url=server.url,
            static_headers=headers,
            forward_headers=server.forward_headers,
            auth_mode=server.auth_mode,
            identity_mode=server.identity_mode,
            send_identity_header=server.send_identity_header,
            protocol_mode=server.protocol_mode,
            listing_snapshot=server.listing_snapshot,
            upstream_oauth=await self._client(server, include_secrets),
        )

    async def _client(
        self, server: McpServer, include_secrets: bool
    ) -> BootstrapOAuthClient | None:
        client = await self._uow.upstream_clients.for_server(server.id)
        if client is None or client.client_id is None:
            return None
        if not client.metadata_.is_admin_stored:
            return None
        secret: str | SecretRef | None = None
        if client.client_secret_encrypted:
            secret = (
                self._cipher.decrypt(client.client_secret_encrypted)
                if include_secrets and self._cipher is not None
                else SecretRef(name=CLIENT_SECRET)
            )
        endpoints = client.metadata_.endpoints
        return BootstrapOAuthClient.model_validate(
            {
                "client_id": client.client_id,
                "client_secret": secret,
                "authorization_url": endpoints.authorization_endpoint if endpoints else None,
                "token_url": endpoints.token_endpoint if endpoints else None,
                "grant_type": client.metadata_.grant,
            }
        )

    async def _bundle(self, bundle: Bundle, names: dict) -> BootstrapBundle:
        memberships = sorted(
            await self._uow.memberships.for_bundle(bundle.id), key=lambda m: m.position
        )
        curations = await self._uow.curations.for_bundle(bundle.id)
        tools = {
            tool.id: tool
            for tool in await self._uow.tools.for_servers([m.server_id for m in memberships])
        }
        members = []
        for membership in memberships:
            curated = [
                BootstrapCuration(
                    tool=tools[curation.tool_id].name,
                    enabled=curation.enabled,
                    override_name=curation.override_name,
                    override_title=curation.override_title,
                    override_description=curation.override_description,
                    override_annotations=curation.override_annotations,
                )
                for curation in curations
                if curation.tool_id in tools
                and tools[curation.tool_id].server_id == membership.server_id
            ]
            members.append(
                BootstrapMember(
                    name=names[membership.server_id],
                    enabled=membership.enabled,
                    tools=sorted(curated, key=lambda c: c.tool),
                )
            )
        prompts = (
            await self._uow.bundle_prompts.page_for_bundle(bundle.id, offset=0, limit=EVERYTHING)
        ).items
        resources = (
            await self._uow.bundle_resources.page_for_bundle(bundle.id, offset=0, limit=EVERYTHING)
        ).items
        return BootstrapBundle(
            name=bundle.name,
            description=bundle.description,
            overview=bundle.overview,
            upstreams=list(members),
            resources=[
                BundleResourceUpsert.model_validate(r.model_dump(), from_attributes=False)
                for r in resources
            ],
            prompts=[BundlePromptUpsert.model_validate(p.model_dump()) for p in prompts],
        )

    @staticmethod
    def _endpoint(endpoint: Endpoint, bundle_names: dict) -> EndpointUpsert:
        return EndpointUpsert.model_validate(
            {
                "name": endpoint.name,
                "bundle_name": bundle_names[endpoint.bundle_id],
                "profile": endpoint.profile,
                "auth_modes": endpoint.auth_modes,
                "rate_limit": endpoint.rate_limit,
                "enabled": endpoint.enabled,
                "allowed_origins": endpoint.allowed_origins,
                "allow_unauthenticated": endpoint.auth_modes == [EndpointAuthMode.NONE],
            }
        )
