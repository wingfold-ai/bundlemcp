"""Stateless MCP adapter: self-describing per-request _meta, no Valkey session."""

import uuid
from collections.abc import Mapping
from typing import Any

from fastapi import Response
from mcp.shared.inbound import (
    ERROR_CODE_HTTP_STATUS,
    InboundLadderRejection,
    classify_inbound_request,
)
from mcp.types import INVALID_PARAMS, INVALID_REQUEST, LOG_LEVEL_META_KEY

from bundlemcp.api.mcp.dispatch.method_registry import MethodRegistry
from bundlemcp.api.mcp.protocol.dialect import DialectRegistry
from bundlemcp.api.mcp.protocol.endpoint_context import EndpointContext
from bundlemcp.api.mcp.protocol.jsonrpc import rpc_error
from bundlemcp.api.mcp.protocol.jsonrpc_message import JsonRpcMessage
from bundlemcp.api.mcp.protocol.request_context import RequestContext
from bundlemcp.api.mcp.protocol.request_rejected import RequestRejected
from bundlemcp.domain.sessions.log_levels import LOG_LEVELS


def _lowercase(headers: Mapping[str, str]) -> dict[str, str]:
    return {name.lower(): value for name, value in headers.items()}


def _rejection(
    message: JsonRpcMessage, code: int, text: str, data: dict[str, Any] | None
) -> Response:
    return rpc_error(
        message.id, code, text, status=ERROR_CODE_HTTP_STATUS.get(code, 400), data=data
    )


class StatelessMcpAdapter:
    """Serves stateless (self-describing) MCP requests."""

    def __init__(self, dialects: DialectRegistry, methods: MethodRegistry) -> None:
        self._dialects = dialects
        self._methods = methods

    async def handle_post(
        self, ctx: EndpointContext, message: JsonRpcMessage, endpoint_name: str
    ) -> Response:
        try:
            request_ctx = self._admit_stateless(ctx, message)
        except RequestRejected as rejected:
            return rejected.response

        if message.is_response:
            return rpc_error(
                None,
                INVALID_REQUEST,
                "a modern-era client sends requests and notifications only",
                status=400,
            )
        return await self._methods.dispatch(request_ctx, message)

    def _admit_stateless(self, ctx: EndpointContext, message: JsonRpcMessage) -> RequestContext:
        # the era comes from the envelope, and the headers mirror the body
        """Validate the per-request envelope and mirrored headers."""
        route = classify_inbound_request(
            message.body(),
            headers=_lowercase(ctx.request.headers),
            supported_modern_versions=self._dialects.modern_versions,
        )
        if isinstance(route, InboundLadderRejection):
            raise RequestRejected(_rejection(message, route.code, route.message, route.data))
        dialect = self._dialects.modern(route.protocol_version)
        if dialect is None:  # pragma: no cover - the ladder already checked the version
            raise RequestRejected(
                _rejection(message, INVALID_PARAMS, "unsupported protocol version", None)
            )
        log_level = message.meta.get(LOG_LEVEL_META_KEY)
        if log_level is not None and log_level not in LOG_LEVELS:
            raise RequestRejected(
                _rejection(message, INVALID_PARAMS, f"unknown log level {log_level!r}", None)
            )
        capabilities = route.client_capabilities
        return RequestContext(
            request=ctx.request,
            view=ctx.view,
            identity=ctx.identity,
            dialect=dialect,
            client_capabilities=dict(capabilities) if isinstance(capabilities, Mapping) else {},
            log_level=log_level,
            routing_key=uuid.uuid4().hex,  # no session, a per-request key
            session=None,
        )
