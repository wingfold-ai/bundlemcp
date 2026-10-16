"""The admin UI's MCP inspector: one operation against one target at a time."""

import asyncio
import time
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any

import structlog
from pydantic import BaseModel, ConfigDict, Field

from bundlemcp.application.contracts.inspection.gateway_endpoint_client_factory import (
    GatewayEndpointClientFactory,
)
from bundlemcp.application.contracts.inspection.inspector_client import InspectorClient
from bundlemcp.application.contracts.inspection.inspector_connector import InspectorConnector
from bundlemcp.application.contracts.inspection.inspector_request_failed import (
    InspectorRequestFailed,
)
from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWorkFactory
from bundlemcp.application.errors.conflict_error import ConflictError
from bundlemcp.application.errors.not_found_error import NotFoundError
from bundlemcp.application.errors.precondition_error import PreconditionError
from bundlemcp.application.inspection.connection_state_detail import connection_state_detail
from bundlemcp.application.inspection.inspector_target_error import InspectorTargetError
from bundlemcp.application.schemas.inspector import (
    AdhocInspectorTarget,
    EndpointInspectorTarget,
    InspectorCallOutcome,
    InspectorCallRequest,
    InspectorConnection,
    InspectorFailure,
    InspectorPing,
    InspectorProgress,
    InspectorTarget,
    InspectorTool,
    InspectorToolList,
    UpstreamInspectorTarget,
)
from bundlemcp.application.schemas.servers.server_info_read import ServerInfoRead
from bundlemcp.application.upstream_oauth.upstream_credential_resolver import (
    UpstreamCredentialResolver,
)
from bundlemcp.domain.access.caller_identity import CallerIdentity
from bundlemcp.domain.access.principal import Principal
from bundlemcp.domain.access.principal_kind import PrincipalKind
from bundlemcp.domain.endpoints.endpoint_auth_mode import EndpointAuthMode
from bundlemcp.domain.servers.connection_state import ConnectionState
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.servers.probe_failure import ProbeFailure
from bundlemcp.domain.upstream_oauth.needs_connect import NeedsConnect
from bundlemcp.domain.upstream_oauth.upstream_oauth_not_configured import UpstreamOAuthNotConfigured

log = structlog.get_logger(__name__)

OPERATION_TIMEOUT_SECONDS = 30
CALL_TIMEOUT_SECONDS = 300
ADHOC_SERVER_NAME = "inspector"  # never stored; names the transient ad-hoc target
REDACTED = "[redacted]"
SHORTEST_SCRUBBED = 4  # shorter values would blank out ordinary words

InspectorEvent = InspectorProgress | InspectorCallOutcome | InspectorFailure


class InspectorPlan(BaseModel):
    """How one operation reaches its target, resolved before anything is sent."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    open: Callable[[], AbstractAsyncContextManager[InspectorClient]] = Field(
        description="Connects to the target and initialises"
    )
    secrets: list[str] = Field(
        description="Credential values sent to the target, scrubbed from anything it echoes"
    )
    log_context: dict[str, str] | None = Field(
        description="Fields bound to every log event of the operation; None for endpoint "
        "targets, which are logged and audited as any client of the endpoint"
    )

    def scrub[T: BaseModel](self, model: T) -> T:
        """The model with every credential value the target might echo replaced."""
        text = model.model_dump_json()
        secrets = [s for s in self.secrets if len(s) >= SHORTEST_SCRUBBED]
        if not any(secret in text for secret in secrets):
            return model
        for secret in secrets:
            text = text.replace(secret, REDACTED)
        return type(model).model_validate_json(text)


class InspectorService:
    """Connects to an upstream, an endpoint of this gateway, or an ad-hoc URL, per operation.

    Every operation opens its own connection and closes it, so no inspector
    state outlives the request and any replica serves the next one. Stored
    credentials are applied here and never returned; a value the target
    echoes back is redacted. Upstream and ad-hoc operations are logged with
    ``source=inspector`` and write no audit record; endpoint operations go
    through the endpoint's public route, where they are audited and metered
    like any client's.
    """

    def __init__(
        self,
        units: UnitOfWorkFactory,
        connector: InspectorConnector,
        endpoints: GatewayEndpointClientFactory,
        credentials: UpstreamCredentialResolver,
    ) -> None:
        self._units = units
        self._connector = connector
        self._endpoints = endpoints
        self._credentials = credentials

    async def connect(
        self, target: InspectorTarget, principal: Principal, client_ip: str
    ) -> InspectorConnection:
        plan = await self._plan(target, principal, client_ip)
        async with self._operation(plan, "initialize") as (client, initialize_ms):
            server = client.server
            info = (
                ServerInfoRead(
                    name=server.name,
                    title=server.title,
                    description=server.description,
                    version=server.version,
                    website_url=server.website_url,
                )
                if server.name is not None
                else None
            )
            return plan.scrub(
                InspectorConnection(
                    server_info=info,
                    protocol_version=server.protocol_version,
                    capabilities=server.capabilities,
                    instructions=server.instructions,
                    initialize_ms=initialize_ms,
                )
            )

    async def ping(
        self, target: InspectorTarget, principal: Principal, client_ip: str
    ) -> InspectorPing:
        plan = await self._plan(target, principal, client_ip)
        async with self._operation(plan, "ping") as (client, initialize_ms):
            started = time.perf_counter()
            await client.ping()
            return InspectorPing(initialize_ms=initialize_ms, duration_ms=_since(started))

    async def list_tools(
        self, target: InspectorTarget, principal: Principal, client_ip: str
    ) -> InspectorToolList:
        plan = await self._plan(target, principal, client_ip)
        async with self._operation(plan, "tools/list") as (client, initialize_ms):
            started = time.perf_counter()
            listed = await client.list_tools()
            return plan.scrub(
                InspectorToolList(
                    tools=[_tool(entry) for entry in listed],
                    initialize_ms=initialize_ms,
                    duration_ms=_since(started),
                )
            )

    async def call_tool(
        self, body: InspectorCallRequest, principal: Principal, client_ip: str
    ) -> AsyncIterator[InspectorEvent]:
        """The call's events: progress as it arrives, then one outcome or failure.

        Resolving the target happens before this returns, so an unknown target
        or a refused credential is an error response rather than a stream.
        """
        plan = await self._plan(body.target, principal, client_ip)
        return self._call_events(plan, body)

    async def _call_events(
        self, plan: InspectorPlan, body: InspectorCallRequest
    ) -> AsyncIterator[InspectorEvent]:
        events: asyncio.Queue[InspectorEvent | None] = asyncio.Queue()
        task = asyncio.create_task(self._run_call(plan, body, events))
        try:
            while (event := await events.get()) is not None:
                yield plan.scrub(event)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def _run_call(
        self,
        plan: InspectorPlan,
        body: InspectorCallRequest,
        events: asyncio.Queue[InspectorEvent | None],
    ) -> None:
        try:
            async with self._operation(plan, "tools/call", timeout=CALL_TIMEOUT_SECONDS) as (
                client,
                initialize_ms,
            ):
                started = time.perf_counter()

                async def on_progress(
                    progress: float, total: float | None, message: str | None
                ) -> None:
                    events.put_nowait(
                        InspectorProgress(
                            progress=progress,
                            total=total,
                            message=message,
                            elapsed_ms=_since(started),
                        )
                    )

                ended = await client.call_tool(body.tool, body.arguments, on_progress)
                outcome = InspectorCallOutcome(
                    result=ended.result,
                    is_error=ended.result is None or bool(ended.result.get("isError")),
                    error_code=ended.error_code,
                    error_message=ended.error_message,
                    initialize_ms=initialize_ms,
                    duration_ms=_since(started),
                )
                log.info(
                    "inspector.tool_called",
                    tool=body.tool,
                    is_error=outcome.is_error,
                    duration_ms=outcome.duration_ms,
                )
                events.put_nowait(outcome)
        except InspectorTargetError as failure:
            events.put_nowait(
                failure.report
                if failure.report is not None
                else InspectorCallOutcome(
                    is_error=True,
                    error_message=str(failure),
                    initialize_ms=0,
                    duration_ms=0,
                )
            )
        except Exception:
            log.warning("inspector.call_failed", tool=body.tool, exc_info=True)
            events.put_nowait(
                InspectorFailure(
                    connection_state=ConnectionState.ERROR,
                    detail=connection_state_detail(ConnectionState.ERROR),
                )
            )
        finally:
            events.put_nowait(None)

    @asynccontextmanager
    async def _operation(
        self, plan: InspectorPlan, operation: str, *, timeout: float = OPERATION_TIMEOUT_SECONDS
    ) -> AsyncIterator[tuple[InspectorClient, int]]:
        """An open client and how long opening it took, failures mapped to one error."""
        with structlog.contextvars.bound_contextvars(**(plan.log_context or {})):
            started = time.perf_counter()
            try:
                async with asyncio.timeout(timeout), plan.open() as client:
                    yield client, _since(started)
            except TimeoutError as exc:
                timed_out = ProbeFailure("timed out", state=ConnectionState.UNREACHABLE)
                raise self._failure(operation, timed_out) from exc
            except ProbeFailure as exc:
                raise self._failure(operation, exc) from exc
            except InspectorRequestFailed as exc:
                message = plan.scrub(_Message(text=exc.message)).text
                raise InspectorTargetError(
                    f"The target answered {operation} with error {exc.code}: {message}"
                ) from exc

    @staticmethod
    def _failure(operation: str, failure: ProbeFailure) -> InspectorTargetError:
        # only the classified state is reported, never the target's own words,
        # which may echo the credentials the inspector sent
        log.info("inspector.unanswered", operation=operation, connection_state=failure.state)
        report = InspectorFailure(
            connection_state=failure.state, detail=connection_state_detail(failure.state)
        )
        return InspectorTargetError(f"{failure.state}: {report.detail}", report)

    async def _plan(
        self, target: InspectorTarget, principal: Principal, client_ip: str
    ) -> InspectorPlan:
        match target:
            case UpstreamInspectorTarget():
                return await self._upstream_plan(target, principal)
            case EndpointInspectorTarget():
                return await self._endpoint_plan(target, client_ip)
            case AdhocInspectorTarget():
                server = McpServer(
                    name=ADHOC_SERVER_NAME, url=target.url, static_headers=target.headers
                )
                return InspectorPlan(
                    open=lambda: self._connector.open(server, {}),
                    secrets=_credential_values(target.headers),
                    log_context=_inspector_context(principal, target="adhoc"),
                )

    async def _upstream_plan(
        self, target: UpstreamInspectorTarget, principal: Principal
    ) -> InspectorPlan:
        async with self._units.open() as uow:
            server = await uow.servers.by_name(target.name)
        if server is None:
            raise NotFoundError(f"upstream {target.name!r} not found")
        if server.requires_per_user_token and principal.kind is not PrincipalKind.ADMIN:
            raise ConflictError(
                f"upstream {server.name!r} calls with each person's own account, and a service "
                "key has none: inspect it signed in as an admin who connected an account (UI-8)"
            )
        try:
            headers = await self._credentials.headers_for(server, _identity(principal))
        except NeedsConnect as exc:
            raise ConflictError(self._credentials.connect_hint(server)) from exc
        except UpstreamOAuthNotConfigured as exc:
            raise PreconditionError(str(exc)) from exc
        return InspectorPlan(
            open=lambda: self._connector.open(server, headers),
            secrets=_credential_values({**server.static_headers, **headers}),
            log_context={
                **_inspector_context(principal, target="upstream"),
                "server": server.name,
            },
        )

    async def _endpoint_plan(
        self, target: EndpointInspectorTarget, client_ip: str
    ) -> InspectorPlan:
        async with self._units.open() as uow:
            endpoint = await uow.endpoints.by_name(target.name)
        if endpoint is None:
            raise NotFoundError(f"endpoint {target.name!r} not found")
        headers = {"Authorization": f"Bearer {target.credential}"} if target.credential else {}
        return InspectorPlan(
            open=lambda: self._endpoints.open(endpoint.name, headers, client_ip=client_ip),
            secrets=[target.credential] if target.credential else [],
            log_context=None,
        )


class _Message(BaseModel):
    text: str = Field(description="A target's error message, before it is shown")


def _since(started: float) -> int:
    return max(0, round((time.perf_counter() - started) * 1000))


def _identity(principal: Principal) -> CallerIdentity:
    """Whose upstream account an inspector operation uses: the admin's own, or none."""
    if principal.kind is PrincipalKind.ADMIN:
        return CallerIdentity(auth_method=EndpointAuthMode.OAUTH, user_id=principal.user_id)
    return CallerIdentity.with_api_key(uuid.UUID(principal.api_key_id))


def _inspector_context(principal: Principal, *, target: str) -> dict[str, str]:
    context = {"source": "inspector", "inspector_target": target}
    if principal.user_id is not None:
        context["user_id"] = principal.user_id
    if principal.api_key_id is not None:
        context["api_key_id"] = principal.api_key_id
    return context


def _credential_values(headers: dict[str, str]) -> list[str]:
    """Each header value, and a bearer token without its scheme."""
    values = []
    for value in headers.values():
        values.append(value)
        scheme, _, token = value.partition(" ")
        if token and scheme.lower() == "bearer":
            values.append(token)
    return values


def _tool(entry: dict[str, Any]) -> InspectorTool:
    return InspectorTool(
        name=entry["name"],
        title=entry.get("title"),
        description=entry.get("description"),
        input_schema=entry.get("inputSchema") or {},
        output_schema=entry.get("outputSchema"),
        annotations=entry.get("annotations"),
    )
