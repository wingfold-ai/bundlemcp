"""Applying a bootstrap document through the services the API uses."""

import structlog
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import async_sessionmaker

from bundlemcp.bootstrap.bootstrap_document import BootstrapDocument
from bundlemcp.bootstrap.document_loader import load_document
from bundlemcp.schemas import BundleServerUpdate
from bundlemcp.services import BundleService, EndpointService, ServerService

log = structlog.get_logger(__name__)


async def apply_document(
    session_factory: async_sessionmaker, redis: Redis, doc: BootstrapDocument
) -> None:
    """Apply the document through the same services the management API uses, so
    every domain invariant (SRV-*, UPO-6, PROF-6) holds identically. Idempotent
    by natural key."""
    async with session_factory() as db:
        servers = ServerService(db, redis)
        bundles = BundleService(db, redis)
        endpoints = EndpointService(db, redis)
        for s in doc.servers:
            await servers.upsert(s)
        for b in doc.bundles:
            await bundles.upsert(b)
            for server_name in b.servers:
                await bundles.set_member(b.name, server_name, BundleServerUpdate())
        for e in doc.endpoints:
            await endpoints.upsert(e)


async def run_bootstrap(session_factory, redis: Redis, settings) -> None:
    """Apply BOOTSTRAP_FILE if set; strict mode refuses to start on error."""
    if not settings.bootstrap_file:
        return
    try:
        doc = load_document(settings.bootstrap_file)
        await apply_document(session_factory, redis, doc)
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
