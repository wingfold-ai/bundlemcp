"""Probing an upstream server through the MCP client library."""

import httpx2

from bundlemcp.application.contracts.upstream.upstream_client_factory import UpstreamClientFactory
from bundlemcp.application.contracts.upstream.upstream_probe import ProbeResult
from bundlemcp.domain.servers.connection_classifier import classify_refusal
from bundlemcp.domain.servers.connection_state import ConnectionState
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.servers.probe_failure import ProbeFailure
from bundlemcp.domain.servers.probed_server_info import ProbedServerInfo
from bundlemcp.domain.servers.probed_tool import ProbedTool
from bundlemcp.domain.servers.response_log import ResponseLog
from bundlemcp.infrastructure.egress.egress_policy import EgressDenied, HostUnresolvable

TRANSPORT_FAILURES = (httpx2.TransportError, OSError, TimeoutError)


def _in_chain[E: BaseException](
    exc: BaseException, kinds: type[E] | tuple[type[E], ...]
) -> E | None:
    """The first exception of ``kinds`` in ``exc``'s cause chain, including exception groups.

    The MCP client wraps what its connection raised, so an egress denial at
    connect time arrives as the cause of a generic connection error.
    """
    seen: set[int] = set()
    pending: list[BaseException] = [exc]
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, kinds):
            return current
        if isinstance(current, BaseExceptionGroup):
            pending.extend(current.exceptions)
        if (linked := current.__cause__ or current.__context__) is not None:
            pending.append(linked)
    return None


class FastMcpUpstreamProbe:
    """One session per probe: list the tools, read what the connection negotiated.

    A probe that gets no MCP answer raises ``ProbeFailure`` classified from
    the HTTP responses the transport observed, because the MCP client reports
    a refused credential, a missing endpoint and a web page all as one error.
    """

    def __init__(self, client_factory: UpstreamClientFactory) -> None:
        self._client_factory = client_factory

    async def probe(self, server: McpServer, headers: dict[str, str]) -> ProbeResult:
        responses = ResponseLog()
        try:
            client = self._client_factory(server, headers, observer=responses)
            async with client:
                listed = await client.list_tools()
                capabilities = client.server_capabilities
                protocol_version = client.protocol_version
                info = client.server_info
        except HostUnresolvable as exc:
            raise ProbeFailure(str(exc), state=ConnectionState.UNREACHABLE) from exc
        except EgressDenied as exc:
            raise ProbeFailure(str(exc), state=ConnectionState.EGRESS_DENIED) from exc
        except Exception as exc:
            if (unresolved := _in_chain(exc, HostUnresolvable)) is not None:
                raise ProbeFailure(str(unresolved), state=ConnectionState.UNREACHABLE) from exc
            if (denied := _in_chain(exc, EgressDenied)) is not None:
                raise ProbeFailure(str(denied), state=ConnectionState.EGRESS_DENIED) from exc
            observed = responses.last
            unreachable = observed is None and _in_chain(exc, TRANSPORT_FAILURES) is not None
            state = classify_refusal(observed, unreachable=unreachable)
            message = f"HTTP {observed.status}: {exc}" if observed is not None else str(exc)
            raise ProbeFailure(message, state=state, observed=observed) from exc
        return ProbeResult(
            tools=[
                ProbedTool(
                    name=tool.name,
                    title=tool.title,
                    description=tool.description,
                    input_schema=tool.input_schema or {},
                    annotations=(
                        tool.annotations.model_dump(exclude_none=True) if tool.annotations else None
                    ),
                )
                for tool in listed
            ],
            capabilities=(
                capabilities.model_dump(mode="json", by_alias=True, exclude_none=True)
                if capabilities is not None
                else None
            ),
            protocol_version=protocol_version,
            server_info=(
                ProbedServerInfo(
                    name=info.name,
                    title=info.title,
                    description=info.description,
                    version=info.version,
                    website_url=info.website_url,
                )
                if info is not None
                else None
            ),
        )
