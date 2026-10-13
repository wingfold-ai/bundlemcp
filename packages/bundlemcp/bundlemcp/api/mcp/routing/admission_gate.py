"""Admission gate: parse envelope and authenticate caller before era dispatch."""

from fastapi import Request
from fastapi.responses import JSONResponse
from mcp.types import PARSE_ERROR
from pydantic import ValidationError

from bundlemcp.api.http.auth_failure_guard import AuthFailureGuard
from bundlemcp.api.mcp.protocol.endpoint_context import EndpointContext
from bundlemcp.api.mcp.protocol.jsonrpc import rpc_error
from bundlemcp.api.mcp.protocol.jsonrpc_message import JsonRpcMessage
from bundlemcp.api.mcp.protocol.request_rejected import RequestRejected
from bundlemcp.api.mcp.routing.authentication import (
    EndpointAuthentication,
    unauthorized_challenge,
)
from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWorkFactory
from bundlemcp.application.serving.bundle_view_loader import load_bundle_view


def _carries_credential(request: Request) -> bool:
    return "authorization" in request.headers or "x-api-key" in request.headers


class AdmissionGate:
    """Encapsulates payload parsing and database admission for the MCP edge."""

    def __init__(
        self,
        *,
        unit_of_work_factory: UnitOfWorkFactory,
        authentication: EndpointAuthentication,
        auth_failures: AuthFailureGuard,
        public_base: str,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._authentication = authentication
        self._auth_failures = auth_failures
        self._public_base = public_base

    async def parse_envelope(self, request: Request) -> JsonRpcMessage:
        """Parse JSON-RPC envelope in-memory (pure CPU, zero DB connections)."""
        try:
            return JsonRpcMessage.parse(await request.json())
        except (ValueError, ValidationError):
            raise RequestRejected(rpc_error(None, PARSE_ERROR, "parse error", status=400)) from None

    async def admit_caller(self, request: Request, endpoint_name: str) -> EndpointContext:
        """Resolve endpoint and authenticate caller via database UnitOfWork."""
        async with self._unit_of_work_factory.open() as uow:
            view = await load_bundle_view(uow, endpoint_name)
            if view is None:
                raise RequestRejected(JSONResponse({"error": "not found"}, status_code=404))
            if _carries_credential(request):
                locked = await self._auth_failures.rejection_if_locked(request)  # EP-20
                if locked is not None:
                    raise RequestRejected(locked)
            identity = await self._authentication.authenticate(request, uow, view)
        if identity is None:
            locked = await self._auth_failures.note_failure(request)  # EP-20
            raise RequestRejected(
                locked or unauthorized_challenge(self._public_base, endpoint_name)
            )
        return EndpointContext(request=request, view=view, identity=identity)
