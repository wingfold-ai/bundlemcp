"""Admission gate: parse envelope and authenticate caller before era dispatch."""

from urllib.parse import urlsplit

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from mcp.types import INVALID_REQUEST, PARSE_ERROR
from pydantic import ValidationError

from bundlemcp.api.http.auth_failure_guard import AuthFailureGuard
from bundlemcp.api.mcp.protocol.cors_grant import CorsGrant
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
from bundlemcp.domain.endpoints.endpoint import Endpoint
from bundlemcp.domain.endpoints.profiles.profile_catalog import ProfileCatalog


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
        profiles: ProfileCatalog,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._authentication = authentication
        self._auth_failures = auth_failures
        self._public_base = public_base
        public = urlsplit(public_base)
        self._public_origin = f"{public.scheme}://{public.netloc}"
        self._profiles = profiles

    def _cors_for(self, request: Request, endpoint: Endpoint) -> CorsGrant:
        """The grant for the request's browser origin, or a 403 if the endpoint refuses it."""
        origin = request.headers.get("origin")
        if origin is None:
            return CorsGrant()  # not a cross-site browser request; auth_modes decide
        if not endpoint.allows_origin(origin, self._public_origin):
            raise RequestRejected(
                rpc_error(None, INVALID_REQUEST, "origin not allowed for this endpoint", status=403)
            )
        return CorsGrant(origin=origin)

    async def preflight(self, request: Request, endpoint_name: str) -> Response:
        """Answer a browser's CORS preflight from the endpoint's allowed origins alone."""
        async with self._unit_of_work_factory.open() as uow:
            endpoint = await uow.endpoints.by_name(endpoint_name)
        if endpoint is None or not endpoint.enabled:
            return JSONResponse({"error": "not found"}, status_code=404)
        try:
            return self._cors_for(request, endpoint).preflight()
        except RequestRejected as rejected:
            return rejected.response

    async def parse_envelope(self, request: Request) -> JsonRpcMessage:
        """Parse JSON-RPC envelope in-memory (pure CPU, zero DB connections)."""
        try:
            return JsonRpcMessage.parse(await request.json())
        except (ValueError, ValidationError):
            raise RequestRejected(rpc_error(None, PARSE_ERROR, "parse error", status=400)) from None

    async def admit_caller(self, request: Request, endpoint_name: str) -> EndpointContext:
        """Resolve endpoint and authenticate caller via database UnitOfWork."""
        async with self._unit_of_work_factory.open() as uow:
            view = await load_bundle_view(uow, endpoint_name, self._profiles)
            if view is None:
                raise RequestRejected(JSONResponse({"error": "not found"}, status_code=404))
            # a browser origin the endpoint refuses is answered before any credential is read
            cors = self._cors_for(request, view.endpoint)
            if _carries_credential(request):
                locked = await self._auth_failures.rejection_if_locked(request)
                if locked is not None:
                    raise RequestRejected(locked, cors)
            identity = await self._authentication.authenticate(request, uow, view)
        if identity is None:
            locked = await self._auth_failures.note_failure(request)
            raise RequestRejected(
                locked or unauthorized_challenge(self._public_base, endpoint_name), cors
            )
        return EndpointContext(request=request, view=view, identity=identity, cors=cors)
