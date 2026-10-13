"""Applying a bootstrap document through the services the API uses."""

import structlog

from bundlemcp.application.bootstrap.bootstrap_document import BootstrapDocument
from bundlemcp.application.bootstrap.document_loader import load_document, parse_document
from bundlemcp.application.bootstrap.probes_after_commit import ProbesAfterCommit
from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWorkFactory
from bundlemcp.application.contracts.secret_cipher import SecretCipher
from bundlemcp.application.contracts.upstream.tool_discovery import ToolDiscovery
from bundlemcp.application.contracts.upstream.upstream_connection_registry import (
    UpstreamConnectionRegistry,
)
from bundlemcp.application.management.bundle_service import BundleService
from bundlemcp.application.management.endpoint_service import EndpointService
from bundlemcp.application.management.server_service import ServerService
from bundlemcp.application.management.upstream_oauth_config_service import (
    UpstreamOAuthConfigService,
)
from bundlemcp.application.schemas import BundleServerUpdate
from bundlemcp.application.settings.settings import Settings

log = structlog.get_logger(__name__)


class BootstrapRunner:
    """Seeds servers, bundles and endpoints from a declarative document.

    The document goes through the same services the management API uses, so
    every domain invariant holds identically, and through one unit of work, so
    a document lands entirely or not at all. Applying it twice changes nothing.
    Every server it upserts is then probed for its tools in the background,
    as after a create through the API, so a fresh gateway serves them without
    a manual refresh; a probe that fails is recorded on the server and never
    fails the bootstrap. A server entry may also name the upstream OAuth client
    the gateway presents to it, stored as the API's client route stores it;
    that needs token encryption keys, so a document naming one without them
    does not apply.
    """

    def __init__(
        self,
        units: UnitOfWorkFactory,
        discovery: ToolDiscovery,
        *,
        cipher: SecretCipher | None,
        connections: UpstreamConnectionRegistry,
    ) -> None:
        # cipher is None exactly when no token encryption keys are configured (DEP-9)
        self._units = units
        self._discovery = discovery
        self._cipher = cipher
        self._connections = connections

    async def apply(self, doc: BootstrapDocument) -> None:
        probes = ProbesAfterCommit(self._discovery)
        async with self._units.open() as uow, uow.atomic():
            servers = ServerService(uow, discovery=probes)
            upstream_clients = UpstreamOAuthConfigService(
                uow, cipher=self._cipher, connections=self._connections
            )
            bundles = BundleService(uow)
            endpoints = EndpointService(uow)
            for server in doc.upstreams:
                await servers.upsert(server)
                if server.upstream_oauth is not None:  # BOOT-9
                    await upstream_clients.set_client(server.name, server.upstream_oauth)
            for bundle in doc.bundles:
                await bundles.upsert(bundle)
                for server_name in bundle.upstreams:
                    await bundles.set_member(bundle.name, server_name, BundleServerUpdate())
            for endpoint in doc.endpoints:
                await endpoints.upsert(endpoint)
        # DISC-1 / BOOT-7: a probe opens its own unit of work, so it must not
        # start before the document's transaction has committed the servers.
        await probes.release()

    async def run(self, settings: Settings) -> None:
        """Apply the configured file, then the inline document.

        Strict mode refuses to start on any error; otherwise it is logged and
        startup continues with whatever applied before it.
        """
        documents: dict[str, BootstrapDocument] = {}
        try:
            if settings.bootstrap_file:  # BOOT-1
                documents["file"] = load_document(settings.bootstrap_file)
            if settings.bootstrap:
                documents["inline"] = parse_document(settings.bootstrap)
            for source, doc in documents.items():
                await self.apply(doc)
                log.info(
                    "bootstrap.applied",
                    source=source,
                    upstreams=len(doc.upstreams),
                    bundles=len(doc.bundles),
                    endpoints=len(doc.endpoints),
                )
        except Exception:
            log.error("bootstrap.failed", strict=settings.bootstrap_strict, exc_info=True)
            if settings.bootstrap_strict:
                raise
