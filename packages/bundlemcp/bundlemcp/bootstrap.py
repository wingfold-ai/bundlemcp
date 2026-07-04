"""Idempotent startup provisioning.

Applies a declarative config document as upserts by natural key, reusing the
same domain rules as the management API. Runs in-process at startup; failures
honor BOOTSTRAP_STRICT.
"""

from pathlib import Path

import structlog
import yaml
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import async_sessionmaker

from bundlemcp.schemas import BundleServerUpdate, BundleUpsert, EndpointUpsert, ServerUpsert
from bundlemcp.services import BundleService, EndpointService, ServerService

log = structlog.get_logger(__name__)


class BootstrapServer(ServerUpsert):
    pass


class BootstrapBundle(BundleUpsert):
    servers: list[str] = []  # member server names (BND-6)


class BootstrapDocument(BaseModel):
    servers: list[BootstrapServer] = []
    bundles: list[BootstrapBundle] = []
    endpoints: list[EndpointUpsert] = []


def load_document(path: str) -> BootstrapDocument:
    data = yaml.safe_load(Path(path).read_text()) or {}
    return BootstrapDocument(**data)


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
