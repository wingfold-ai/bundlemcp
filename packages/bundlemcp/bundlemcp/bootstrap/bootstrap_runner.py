"""Applying a bootstrap document through the services the API uses."""

import structlog

from bundlemcp.bootstrap.bootstrap_document import BootstrapDocument
from bundlemcp.bootstrap.document_loader import load_document
from bundlemcp.schemas import BundleServerUpdate
from bundlemcp.services import BundleService, EndpointService, ServerService, ToolDiscovery
from bundlemcp.settings import Settings
from bundlemcp.store import UnitOfWorkFactory

log = structlog.get_logger(__name__)


class BootstrapRunner:
    """Seeds servers, bundles and endpoints from a declarative document.

    The document goes through the same services the management API uses, so
    every domain invariant holds identically, and through one unit of work, so
    a document lands entirely or not at all. Applying it twice changes nothing.
    """

    def __init__(self, units: UnitOfWorkFactory, discovery: ToolDiscovery) -> None:
        self._units = units
        self._discovery = discovery

    async def apply(self, doc: BootstrapDocument) -> None:
        async with self._units.open() as uow, uow.atomic():
            servers = ServerService(uow, discovery=self._discovery)
            bundles = BundleService(uow)
            endpoints = EndpointService(uow)
            for server in doc.servers:
                await servers.upsert(server)
            for bundle in doc.bundles:
                await bundles.upsert(bundle)
                for server_name in bundle.servers:
                    await bundles.set_member(bundle.name, server_name, BundleServerUpdate())
            for endpoint in doc.endpoints:
                await endpoints.upsert(endpoint)

    async def run(self, settings: Settings) -> None:
        """Apply the configured file if there is one; strict mode refuses to start on error."""
        if not settings.bootstrap_file:
            return
        try:
            doc = load_document(settings.bootstrap_file)
            await self.apply(doc)
            log.info(
                "bootstrap.applied",
                servers=len(doc.servers),
                bundles=len(doc.bundles),
                endpoints=len(doc.endpoints),
            )
        except Exception:
            log.error("bootstrap.failed", strict=settings.bootstrap_strict, exc_info=True)
            if settings.bootstrap_strict:
                raise
