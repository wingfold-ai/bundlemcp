"""Applying a bootstrap document through the services the API uses."""

import os
from collections.abc import Mapping

import structlog

from bundlemcp.application.bootstrap.api_key_value import api_key_value
from bundlemcp.application.bootstrap.bootstrap_document import BootstrapDocument
from bundlemcp.application.bootstrap.document_loader import load_document, parse_document
from bundlemcp.application.bootstrap.probes_after_commit import ProbesAfterCommit
from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWorkFactory
from bundlemcp.application.contracts.secret_cipher import SecretCipher
from bundlemcp.application.contracts.upstream.tool_discovery import ToolDiscovery
from bundlemcp.application.contracts.upstream.upstream_connection_registry import (
    UpstreamConnectionRegistry,
)
from bundlemcp.application.management.api_key_service import ApiKeyService
from bundlemcp.application.management.config_import_service import ConfigImportService
from bundlemcp.application.settings.settings import Settings
from bundlemcp.domain.endpoints.profiles.profile_catalog import ProfileCatalog
from bundlemcp.domain.shared.secret_generator import SecretGenerator
from bundlemcp.domain.shared.secret_hasher import SecretHasher

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
    does not apply. API keys come last, so their scopes can name the
    document's endpoints; a key whose name exists is never touched.
    """

    def __init__(
        self,
        units: UnitOfWorkFactory,
        discovery: ToolDiscovery,
        *,
        cipher: SecretCipher | None,
        connections: UpstreamConnectionRegistry,
        profiles: ProfileCatalog,
        public_base: str,
        hasher: SecretHasher,
        generator: SecretGenerator,
        environ: Mapping[str, str] = os.environ,
    ) -> None:
        # cipher is None exactly when no token encryption keys are configured
        self._units = units
        self._discovery = discovery
        self._cipher = cipher
        self._connections = connections
        self._profiles = profiles
        self._public_base = public_base
        self._hasher = hasher
        self._generator = generator
        self._environ = environ

    async def apply(self, doc: BootstrapDocument) -> None:
        # a referenced key value is checked before anything is written, so a missing
        # variable fails the document without touching the store
        for entry in doc.api_keys:
            if entry.value_from_env is not None:
                api_key_value(entry, environ=self._environ, generate=lambda: "")
        probes = ProbesAfterCommit(self._discovery)
        importer = ConfigImportService(
            self._units,
            self._discovery,
            cipher=self._cipher,
            connections=self._connections,
            profiles=self._profiles,
            public_base=self._public_base,
        )
        async with self._units.open() as uow, uow.atomic():
            # the import route's code path, failing on the first resource that cannot apply
            await importer.apply_in(uow, doc, probes, strict=True)
            keys = ApiKeyService(uow, hasher=self._hasher, generator=self._generator)
            for entry in doc.api_keys:
                if await keys.exists(entry.name):
                    continue  # never overwritten, re-scoped or re-activated
                scope: list[str] = []
                for endpoint_name in entry.endpoints:
                    endpoint = await uow.endpoints.by_name(endpoint_name)
                    if endpoint is None:
                        raise ValueError(
                            f"api key {entry.name!r} is scoped to unknown endpoint "
                            f"{endpoint_name!r} (MGMT-10)"
                        )
                    scope.append(str(endpoint.id))
                value = api_key_value(entry, environ=self._environ, generate=keys.new_value)
                keys.provision(entry.name, entry.kind, scope, value, scopes=entry.scopes)
                log.info(
                    "bootstrap.api_key_provisioned",
                    name=entry.name,
                    kind=entry.kind.value,
                    scopes=[s.value for s in entry.scopes],
                    source="environment" if entry.value_from_env else "file",
                )
        # a probe opens its own unit of work, so it must not
        # start before the document's transaction has committed the servers.
        await probes.release()

    async def run(self, settings: Settings) -> None:
        """Apply the configured file, then the inline document.

        Strict mode refuses to start on any error; otherwise it is logged and
        startup continues with whatever applied before it.
        """
        documents: dict[str, BootstrapDocument] = {}
        try:
            if settings.bootstrap_file:
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
                    api_keys=len(doc.api_keys),
                )
        except Exception:
            log.error("bootstrap.failed", strict=settings.bootstrap_strict, exc_info=True)
            if settings.bootstrap_strict:
                raise
