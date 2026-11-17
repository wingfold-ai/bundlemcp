"""Applying a configuration document: the import route and bootstrap share this."""

from typing import Any

from pydantic import ValidationError

from bundlemcp.application.bootstrap.bootstrap_bundle import BootstrapBundle
from bundlemcp.application.bootstrap.bootstrap_document import BootstrapDocument
from bundlemcp.application.bootstrap.bootstrap_oauth_client import BootstrapOAuthClient
from bundlemcp.application.bootstrap.bootstrap_server import BootstrapServer
from bundlemcp.application.bootstrap.probes_after_commit import ProbesAfterCommit
from bundlemcp.application.bootstrap.secret_ref import SecretRef
from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWork, UnitOfWorkFactory
from bundlemcp.application.contracts.secret_cipher import SecretCipher
from bundlemcp.application.contracts.upstream.tool_discovery import ToolDiscovery
from bundlemcp.application.contracts.upstream.upstream_connection_registry import (
    UpstreamConnectionRegistry,
)
from bundlemcp.application.errors import InvalidInputError, NotFoundError, ServiceError
from bundlemcp.application.management.bundle_prompt_service import BundlePromptService
from bundlemcp.application.management.bundle_resource_service import BundleResourceService
from bundlemcp.application.management.bundle_service import BundleService
from bundlemcp.application.management.endpoint_service import EndpointService
from bundlemcp.application.management.server_service import ServerService
from bundlemcp.application.management.upstream_oauth_config_service import (
    UpstreamOAuthConfigService,
)
from bundlemcp.application.schemas import (
    BundleServerUpdate,
    BundleToolUpdate,
    EndpointUpsert,
    ImportOutcome,
    ImportReport,
    ImportResult,
    ServerUpsert,
    UpstreamOAuthConfig,
)
from bundlemcp.domain.access.principal import Principal
from bundlemcp.domain.endpoints.profiles.profile_catalog import ProfileCatalog
from bundlemcp.domain.servers.url_change import UrlChange

# what changes on every write without being configuration
VOLATILE = {"created_at", "updated_at", "last_used_at"}
NOT_DISCOVERED = "tool not discovered yet; re-import after discovery"


class DocumentDiscarded(Exception):
    """Raised inside the document's transaction to roll it back: a dry run, or an error."""


class ConfigImportService:
    """Applies a document as upserts by natural key, in one transaction, and reports each resource.

    Every resource goes through the service the management API uses, so each
    rule holds exactly as it does there. A resource is ``skipped`` when applying
    it changed nothing. When any resource errors, or on a dry run, the whole
    transaction is rolled back, and the servers it touched are probed only after
    a real commit. Nothing absent from the document is deleted.

    A placeholder keeps the value the target stores; with nothing stored, the
    resource errors. A tool's curation names the tool as its upstream does; one
    not discovered yet is skipped, so re-importing after discovery completes it.
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
    ) -> None:
        # cipher is None exactly when no token encryption keys are configured
        self._units = units
        self._discovery = discovery
        self._cipher = cipher
        self._connections = connections
        self._profiles = profiles
        self._public_base = public_base

    async def run(
        self, doc: BootstrapDocument, *, dry_run: bool, actor: Principal | None = None
    ) -> ImportReport:
        """Import ``doc``; with ``dry_run`` report what would happen and write nothing.

        Management actions the import causes are recorded against ``actor``.
        """
        if doc.api_keys:
            # keys are identity, not configuration: only a bootstrap document provisions them
            refused = [
                ImportResult(
                    kind="api_key",
                    name=entry.name,
                    outcome=ImportOutcome.ERROR,
                    message="an import never creates API keys; provision them from the bootstrap "
                    "document (MGMT-21)",
                )
                for entry in doc.api_keys
            ]
            return ImportReport(dry_run=dry_run, applied=False, results=refused)
        probes = ProbesAfterCommit(self._discovery)
        results: list[ImportResult] = []
        applied = False
        try:
            async with self._units.open() as uow, uow.atomic():
                results = await self.apply_in(uow, doc, probes, strict=False, actor=actor)
                if dry_run or any(r.outcome is ImportOutcome.ERROR for r in results):
                    raise DocumentDiscarded
            applied = True
        except DocumentDiscarded:
            pass
        if applied:
            await probes.release()
        return ImportReport(dry_run=dry_run, applied=applied, results=results)

    async def apply_in(
        self,
        uow: UnitOfWork,
        doc: BootstrapDocument,
        discovery: ToolDiscovery,
        *,
        strict: bool,
        actor: Principal | None = None,
    ) -> list[ImportResult]:
        """Apply the document's resources in ``uow``; the caller owns the transaction.

        ``strict`` lets the first failure propagate, as bootstrap wants; otherwise
        each failure becomes that resource's ``error`` and the rest still run.
        """
        session = _Session(
            uow,
            discovery,
            cipher=self._cipher,
            connections=self._connections,
            profiles=self._profiles,
            public_base=self._public_base,
            strict=strict,
            actor=actor,
        )
        for server in doc.upstreams:
            await session.upstream(server)
        for bundle in doc.bundles:
            await session.bundle(bundle)
        for endpoint in doc.endpoints:
            await session.endpoint(endpoint)
        return session.results


class _Session:
    """One document's application: the services in one unit of work, and the results so far."""

    def __init__(
        self,
        uow: UnitOfWork,
        discovery: ToolDiscovery,
        *,
        cipher: SecretCipher | None,
        connections: UpstreamConnectionRegistry,
        profiles: ProfileCatalog,
        public_base: str,
        strict: bool,
        actor: Principal | None,
    ) -> None:
        self._uow = uow
        self._strict = strict
        self._actor = actor
        self.results: list[ImportResult] = []
        self._servers = ServerService(uow, discovery=discovery, public_base=public_base)
        self._clients = UpstreamOAuthConfigService(uow, cipher=cipher, connections=connections)
        self._bundles = BundleService(uow, public_base=public_base)
        self._prompts = BundlePromptService(uow)
        self._resources = BundleResourceService(uow)
        self._endpoints = EndpointService(uow, profiles=profiles)

    def _report(self, kind: str, name: str, before: Any, after: Any) -> None:
        if before is None:
            outcome = ImportOutcome.CREATED
        elif before == after:
            outcome = ImportOutcome.SKIPPED
        else:
            outcome = ImportOutcome.UPDATED
        self.results.append(ImportResult(kind=kind, name=name, outcome=outcome))

    def _fail(self, kind: str, name: str, error: Exception) -> None:
        if self._strict:
            raise error
        self.results.append(
            ImportResult(kind=kind, name=name, outcome=ImportOutcome.ERROR, message=str(error))
        )

    # ---- upstreams ----

    async def _upstream_state(self, name: str) -> Any:
        server = await self._uow.servers.by_name(name)
        if server is None:
            return None
        client = await self._uow.upstream_clients.for_server(server.id)
        return (
            _plain(server),
            _plain(client) if client is not None else None,
        )

    async def upstream(self, entry: BootstrapServer) -> None:
        before = await self._upstream_state(entry.name)
        try:
            await self._servers.upsert(await self._server_upsert(entry), actor=self._actor)
            if entry.upstream_oauth is not None:
                await self._clients.set_client(
                    entry.name, await self._oauth_client(entry.name, entry.upstream_oauth)
                )
        except (ServiceError, ValidationError) as error:
            self._fail("upstream", entry.name, error)
            return
        self._report("upstream", entry.name, before, await self._upstream_state(entry.name))

    async def _server_upsert(self, entry: BootstrapServer) -> ServerUpsert:
        """The API's upsert for ``entry``, a placeholder replaced by the value stored for it."""
        stored = await self._uow.servers.by_name(entry.name)
        stored_headers = stored.static_headers if stored is not None else {}
        moves_origin = (
            stored is not None and UrlChange(previous=stored.url, current=entry.url).moves_origin
        )
        headers: dict[str, str] = {}
        for header, value in entry.static_headers.items():
            if isinstance(value, SecretRef):
                if header not in stored_headers:
                    raise InvalidInputError(
                        f"static header {header!r} is a placeholder, but nothing is stored for "
                        "it (MGMT-18)"
                    )
                if moves_origin:
                    raise InvalidInputError(
                        f"static header {header!r} is a placeholder, but the url moves to another "
                        "origin; give its value (UPS-42)"
                    )
                headers[header] = stored_headers[header]
            else:
                headers[header] = value
        body = entry.model_dump(exclude={"upstream_oauth", "static_headers"})
        return ServerUpsert.model_validate({**body, "static_headers": headers})

    async def _oauth_client(self, name: str, client: BootstrapOAuthClient) -> UpstreamOAuthConfig:
        secret = client.client_secret
        if isinstance(secret, SecretRef):
            server = await self._uow.servers.by_name(name)
            stored = await self._uow.upstream_clients.for_server(server.id) if server else None
            if stored is None or not stored.client_secret_encrypted:
                raise InvalidInputError(
                    "the upstream OAuth client secret is a placeholder, but nothing is stored "
                    "for it (MGMT-18)"
                )
            secret = None  # absent keeps the stored secret
        return UpstreamOAuthConfig.model_validate(
            {**client.model_dump(exclude={"client_secret"}), "client_secret": secret}
        )

    # ---- bundles ----

    async def _bundle_state(self, name: str) -> Any:
        bundle = await self._uow.bundles.by_name(name)
        if bundle is None:
            return None
        members = await self._uow.memberships.for_bundle(bundle.id)
        curations = await self._uow.curations.for_bundle(bundle.id)
        prompts = (
            await self._uow.bundle_prompts.page_for_bundle(bundle.id, offset=0, limit=10_000)
        ).items
        resources = (
            await self._uow.bundle_resources.page_for_bundle(bundle.id, offset=0, limit=10_000)
        ).items
        return (
            _plain(bundle),
            sorted(_plain(m, "id") for m in members),
            sorted(_plain(c, "id") for c in curations),
            sorted(_plain(p, "id") for p in prompts),
            sorted(_plain(r, "id") for r in resources),
        )

    async def bundle(self, entry: BootstrapBundle) -> None:
        before = await self._bundle_state(entry.name)
        try:
            await self._bundles.upsert(entry)
            for member in entry.members:
                await self._bundles.set_member(
                    entry.name, member.name, BundleServerUpdate(enabled=member.enabled)
                )
            await self._bundles.place_members_first(
                entry.name, [member.name for member in entry.members]
            )
            # resources first, since a prompt may embed one
            for resource in entry.resources:
                await self._resources.upsert(entry.name, resource)
            for prompt in entry.prompts:
                await self._prompts.upsert(entry.name, prompt)
            skipped = await self._curate(entry)
        except (ServiceError, ValidationError) as error:
            self._fail("bundle", entry.name, error)
            return
        self._report("bundle", entry.name, before, await self._bundle_state(entry.name))
        self.results.extend(skipped)

    async def _curate(self, entry: BootstrapBundle) -> list[ImportResult]:
        """Apply each member's curation; a tool not in the cache yet is skipped, not failed."""
        skipped: list[ImportResult] = []
        for member in entry.members:
            if not member.tools:
                continue
            server = await self._uow.servers.by_name(member.name)
            if server is None:
                raise NotFoundError(f"upstream {member.name!r} not found")
            by_name = {tool.name: tool for tool in await self._uow.tools.for_server(server.id)}
            for curation in member.tools:
                tool = by_name.get(curation.tool)
                if tool is None:
                    skipped.append(
                        ImportResult(
                            kind="curation",
                            name=f"{entry.name}/{member.name}/{curation.tool}",
                            outcome=ImportOutcome.SKIPPED,
                            message=NOT_DISCOVERED,
                        )
                    )
                    continue
                await self._bundles.curate_tool(
                    entry.name,
                    tool.id,
                    BundleToolUpdate.model_validate(curation.model_dump(exclude={"tool"})),
                )
        return skipped

    # ---- endpoints ----

    async def _endpoint_state(self, name: str) -> Any:
        endpoint = await self._uow.endpoints.by_name(name)
        return _plain(endpoint) if endpoint is not None else None

    async def endpoint(self, entry: EndpointUpsert) -> None:
        before = await self._endpoint_state(entry.name)
        try:
            await self._endpoints.upsert(entry)
        except (ServiceError, ValidationError) as error:
            self._fail("endpoint", entry.name, error)
            return
        self._report("endpoint", entry.name, before, await self._endpoint_state(entry.name))


def _plain(entity: Any, *drop: str) -> str:
    """A comparable rendering of an entity's configuration, without its bookkeeping fields."""
    return entity.model_dump_json(exclude=VOLATILE | set(drop))
