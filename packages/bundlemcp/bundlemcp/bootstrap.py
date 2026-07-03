"""Idempotent startup provisioning.

Applies a declarative config document as upserts by natural key, reusing the
same domain rules as the management API. Runs in-process at startup; failures
honor BOOTSTRAP_STRICT.
"""

from pathlib import Path

import structlog
import yaml
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import select

from bundlemcp.api.schemas import BundleUpsert, EndpointUpsert, ServerUpsert
from bundlemcp.models import Bundle, BundleServer, Endpoint, McpServer

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


async def apply_document(session_factory: async_sessionmaker, doc: BootstrapDocument) -> None:
    async with session_factory() as db:
        for s in doc.servers:
            server = (
                await db.execute(select(McpServer).where(McpServer.name == s.name))
            ).scalar_one_or_none()
            if server is None:
                server = McpServer(name=s.name, url=s.url)
            server.description = s.description
            server.url = s.url
            if s.static_headers:
                server.static_headers = s.static_headers
            server.forward_headers = s.forward_headers
            server.auth_mode = s.auth_mode
            db.add(server)
        await db.commit()

        for b in doc.bundles:
            bundle = (
                await db.execute(select(Bundle).where(Bundle.name == b.name))
            ).scalar_one_or_none()
            if bundle is None:
                bundle = Bundle(name=b.name)
            bundle.description = b.description
            db.add(bundle)
            await db.commit()
            await db.refresh(bundle)
            for server_name in b.servers:
                server = (
                    await db.execute(select(McpServer).where(McpServer.name == server_name))
                ).scalar_one_or_none()
                if server is None:
                    raise ValueError(f"bundle {b.name}: unknown server {server_name}")
                exists = (
                    await db.execute(
                        select(BundleServer).where(
                            BundleServer.bundle_id == bundle.id,
                            BundleServer.server_id == server.id,
                        )
                    )
                ).scalar_one_or_none()
                if exists is None:
                    db.add(BundleServer(bundle_id=bundle.id, server_id=server.id))
            await db.commit()

        for e in doc.endpoints:
            bundle = (
                await db.execute(select(Bundle).where(Bundle.name == e.bundle_name))
            ).scalar_one_or_none()
            if bundle is None:
                raise ValueError(f"endpoint {e.name}: unknown bundle {e.bundle_name}")
            endpoint = (
                await db.execute(select(Endpoint).where(Endpoint.name == e.name))
            ).scalar_one_or_none()
            if endpoint is None:
                endpoint = Endpoint(name=e.name, bundle_id=bundle.id)
            endpoint.bundle_id = bundle.id
            endpoint.profile = e.profile
            endpoint.auth_modes = [m.value for m in e.auth_modes]
            endpoint.rate_limit = e.rate_limit
            endpoint.enabled = e.enabled
            db.add(endpoint)
        await db.commit()


async def run_bootstrap(session_factory, settings) -> None:
    """Apply BOOTSTRAP_FILE if set; strict mode refuses to start on error."""
    if not settings.bootstrap_file:
        return
    try:
        doc = load_document(settings.bootstrap_file)
        await apply_document(session_factory, doc)
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
