"""Admission gate: parse envelope and authenticate caller before era dispatch."""

from urllib.parse import urlsplit

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from mcp.types import INVALID_REQUEST, PARSE_ERROR
from pydantic import ValidationError

from bundlemcp.api.http.auth_failure_guard import AuthFailureGuard
from bundlemcp.api.http.log_context import bind_caller, bind_request_fields
from bundlemcp.api.mcp.protocol.cors_grant import CorsGrant
from bundlemcp.api.mcp.protocol.endpoint_context import EndpointContext
from bundlemcp.api.mcp.protocol.jsonrpc import rpc_error
from bundlemcp.api.mcp.protocol.jsonrpc_message import JsonRpcMessage
from bundlemcp.api.mcp.protocol.request_rejected import RequestRejected
from bundlemcp.api.mcp.routing.authentication import (
    EndpointAuthentication,
    presents_bearer,
    unauthorized_challenge,
)
from bundlemcp.application.contracts.persistence.audit_sink import AuditSink
from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWorkFactory
from bundlemcp.application.serving.bundle_view_loader import load_bundle_view
from bundlemcp.domain.access.caller_identity import CallerIdentity
from bundlemcp.domain.audit.audit_record import AuditRecord
from bundlemcp.domain.audit.audit_status import AuditStatus
from bundlemcp.domain.bundles.bundle_view import BundleView
from bundlemcp.domain.endpoints.endpoint import Endpoint
from bundlemcp.domain.endpoints.profiles.profile_catalog import ProfileCatalog

# the audit reason of a call whose valid credential is not entitled to the endpoint
FORBIDDEN = "forbidden"


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
        audit: AuditSink,
        public_base: str,
        profiles: ProfileCatalog,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._authentication = authentication
        self._auth_failures = auth_failures
        self._audit = audit
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

    def _audit_forbidden(
        self, view: BundleView, holder: CallerIdentity, message: JsonRpcMessage
    ) -> None:
        if message.method != "tools/call":
            return  # only a call is worth a record; listings stay out of the log
        self._audit.record(
            AuditRecord(
                endpoint_id=view.endpoint.id,
                endpoint_name=view.endpoint.name,
                bundle_name=view.bundle.name,
                presented_tool_name=str(message.param("name", "")) or None,
                user_id=holder.user_uuid,
                api_key_id=holder.api_key_uuid,
                auth_method=holder.auth_method,
                status=AuditStatus.DENIED,
                denied_reason=FORBIDDEN,
            )
        )

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

    async def admit_caller(
        self, request: Request, endpoint_name: str, message: JsonRpcMessage | None = None
    ) -> EndpointContext:
        """Resolve endpoint and authenticate caller via database UnitOfWork.

        A ``tools/call`` (``message``) refused because its valid credential is
        not entitled to the endpoint is audited as denied, ``forbidden``; the
        answer is the same as for any refused credential.
        """
        async with self._unit_of_work_factory.open() as uow:
            view = await load_bundle_view(uow, endpoint_name, self._profiles)
            if view is None:
                raise RequestRejected(JSONResponse({"error": "not found"}, status_code=404))
            bind_request_fields(endpoint=view.endpoint.name)
            # a browser origin the endpoint refuses is answered before any credential is read
            cors = self._cors_for(request, view.endpoint)
            if _carries_credential(request):
                locked = await self._auth_failures.rejection_if_locked(request)
                if locked is not None:
                    raise RequestRejected(locked, cors)
            outcome = await self._authentication.authenticate(request, uow, view)
        identity = outcome.identity
        if identity is None:
            if outcome.forbidden is not None and message is not None:
                self._audit_forbidden(view, outcome.forbidden, message)
            locked = await self._auth_failures.note_failure(request)
            challenge = unauthorized_challenge(
                self._public_base,
                endpoint_name,
                invalid_token=presents_bearer(request.headers.get("authorization")),
            )
            raise RequestRejected(locked or challenge, cors)
        bind_caller(identity)
        return EndpointContext(request=request, view=view, identity=identity, cors=cors)
