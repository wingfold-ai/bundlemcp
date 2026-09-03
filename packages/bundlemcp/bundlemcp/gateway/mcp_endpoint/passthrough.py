"""Read-only passthrough: prompts, resources and completions.

Live and uncurated, unlike the tool surface: each request fans out to the
enabled member servers. Prompt names are prefixed `server__prompt`; resource
URIs pass through unchanged and are routed on read by fan-out, first owner
wins. No metering and no tool-call audit — these are reads.
"""

import asyncio
import uuid
from typing import Any

import structlog
from fastapi import Request, Response
from mcp.types import PromptReference, ResourceTemplateReference

from bundlemcp.gateway.mcp_endpoint.forwarded_headers import forwarded_headers
from bundlemcp.gateway.mcp_endpoint.gateway_runtime import GatewayRuntime
from bundlemcp.gateway.mcp_endpoint.jsonrpc import rpc_error, rpc_result
from bundlemcp.models import IdentityMode, PresentedName, ServerAuthMode
from bundlemcp.oauth.upstream_client import NeedsConnect
from bundlemcp.store.sessions import SessionRecord

log = structlog.get_logger(__name__)


async def _readonly_headers(
    runtime: GatewayRuntime, request: Request, server, record: SessionRecord
) -> dict[str, str]:
    """Forward headers + upstream-OAuth bearer for a read-only member call.

    Raises NeedsConnect if an upstream_oauth member has no usable token.
    """
    headers = forwarded_headers(request.headers, server, record.identity.sub)
    if server.auth_mode == ServerAuthMode.UPSTREAM_OAUTH:
        if runtime.upstream_tokens is None:
            raise NeedsConnect("upstream_oauth_not_configured")
        token_user: uuid.UUID | None = None
        if server.identity_mode == IdentityMode.PER_USER:
            token_user = record.identity.user_uuid
            if token_user is None:
                raise NeedsConnect("per_user_requires_user")
        access = await runtime.upstream_tokens.ensure_access_token(server, token_user)
        headers["Authorization"] = f"Bearer {access}"
    return headers


def _connect_hint(runtime: GatewayRuntime, server) -> str:
    suffix = "?as=me" if server.identity_mode == IdentityMode.PER_USER else ""
    url = f"{runtime.public_url}/oauth/upstream/{server.name}/connect{suffix}"
    return f"upstream not connected — connect at {url}"


async def _fanout_readonly(runtime, request, record, servers, call):
    """Run `call(client)` against each member concurrently; skip + WARN failures.

    Returns a list of (server, result | None) — a None means that member was
    unreachable/unconnected and was omitted (DISC-4: degrade observably).
    """

    async def _one(server):
        try:
            headers = await _readonly_headers(runtime, request, server, record)
        except NeedsConnect:
            log.warning("passthrough.member_unconnected", server=server.name)
            return server, None
        try:
            client = runtime.client_factory(server, headers)
            async with client:
                return server, await call(client)
        except Exception:
            log.warning("passthrough.member_failed", server=server.name, exc_info=True)
            return server, None

    return list(await asyncio.gather(*[_one(s) for s in servers]))


def _dump(obj) -> dict[str, Any]:
    return obj.model_dump(by_alias=True, mode="json", exclude_none=True)


async def handle_prompts_list(runtime, request, view, record, rpc_id) -> Response:
    """PROT-11/BND-8: merge members' prompts with `server__name` prefixing."""

    async def call(client):
        return await client.list_prompts()

    prompts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for server, member_prompts in await _fanout_readonly(
        runtime, request, record, view.servers.values(), call
    ):
        if member_prompts is None:
            continue
        for prompt in member_prompts:
            entry = _dump(prompt)
            entry["name"] = PresentedName(server=server.name, name=prompt.name).text
            if entry["name"] in seen:
                continue
            seen.add(entry["name"])
            prompts.append(entry)
    return rpc_result(rpc_id, {"prompts": prompts})


async def handle_prompts_get(runtime, request, view, record, body, rpc_id) -> Response:
    params = body.get("params") or {}
    presented = params.get("name", "")
    parsed = PresentedName.parse(presented)  # BND-2 first-`__`
    server = view.servers.get(parsed.server) if parsed else None
    if parsed is None or server is None:
        return rpc_error(rpc_id, -32602, f"unknown prompt: {presented}")
    prompt_name = parsed.name
    try:
        headers = await _readonly_headers(runtime, request, server, record)
    except NeedsConnect:
        return rpc_error(rpc_id, -32000, _connect_hint(runtime, server))
    try:
        client = runtime.client_factory(server, headers)
        async with client:
            result = await client.get_prompt_mcp(prompt_name, params.get("arguments") or None)
    except Exception as exc:
        log.warning("prompts.get_failed", server=server.name)
        return rpc_error(rpc_id, -32000, str(exc)[:200])
    return rpc_result(rpc_id, _dump(result))


async def handle_completion(runtime, request, view, record, body, rpc_id) -> Response:
    """PROT-9: route completion to the owning member (prompt ref de-prefixed;
    resource-template ref resolved by URI fan-out)."""
    params = body.get("params") or {}
    ref = params.get("ref") or {}
    argument = params.get("argument") or {}
    context = (params.get("context") or {}).get("arguments")

    if ref.get("type") == "ref/prompt":
        presented = ref.get("name", "")
        parsed = PresentedName.parse(presented)
        server = view.servers.get(parsed.server) if parsed else None
        if parsed is None or server is None:
            return rpc_error(rpc_id, -32602, f"unknown prompt ref: {presented}")
        member_ref = PromptReference(type="ref/prompt", name=parsed.name)
        candidates = [server]
    elif ref.get("type") == "ref/resource":
        member_ref = ResourceTemplateReference(type="ref/resource", uri=ref.get("uri", ""))
        candidates = list(view.servers.values())  # URI is not prefixed → fan-out
    else:
        return rpc_error(rpc_id, -32602, f"unsupported completion ref: {ref.get('type')}")

    for server in candidates:
        try:
            headers = await _readonly_headers(runtime, request, server, record)
            client = runtime.client_factory(server, headers)
            async with client:
                result = await client.complete_mcp(member_ref, argument, context)
            return rpc_result(rpc_id, _dump(result))
        except Exception:
            log.warning("completion.member_failed", server=server.name)
            continue
    return rpc_result(rpc_id, {"completion": {"values": [], "hasMore": False}})


async def _merge_by_key(runtime, request, view, record, call, key: str) -> list[dict[str, Any]]:
    """Fan-out a resource-list method, merging entries de-duplicated by `key`."""
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for server, member in await _fanout_readonly(
        runtime, request, record, view.servers.values(), call
    ):
        if member is None:
            continue
        for obj in member:
            entry = _dump(obj)
            identity = entry.get(key)
            if identity in seen:
                log.warning("resources.collision", key=identity, server=server.name)
                continue
            seen.add(identity)
            items.append(entry)
    return items


async def handle_resources_list(runtime, request, view, record, rpc_id) -> Response:
    """BND-8: merge members' resources; URIs pass through unchanged (dedupe by URI)."""

    async def call(client):
        return await client.list_resources()

    items = await _merge_by_key(runtime, request, view, record, call, "uri")
    return rpc_result(rpc_id, {"resources": items})


async def handle_resource_templates_list(runtime, request, view, record, rpc_id) -> Response:
    async def call(client):
        return await client.list_resource_templates()

    items = await _merge_by_key(runtime, request, view, record, call, "uriTemplate")
    return rpc_result(rpc_id, {"resourceTemplates": items})


async def handle_resources_read(runtime, request, view, record, body, rpc_id) -> Response:
    """BND-8: resolve the owner by fan-out — first enabled member that owns the URI."""
    uri = (body.get("params") or {}).get("uri", "")
    for server in view.servers.values():
        try:
            headers = await _readonly_headers(runtime, request, server, record)
            client = runtime.client_factory(server, headers)
            async with client:
                result = await client.read_resource_mcp(uri)
            return rpc_result(rpc_id, _dump(result))
        except Exception:
            continue
    return rpc_error(rpc_id, -32002, f"resource not found: {uri}")


async def handle_resources_subscribe(rpc_id) -> Response:
    """Accept the subscription (request/response half).

    notifications/resources/updated push is pooling-dependent (ADR-0021) and is
    not delivered between calls under per-call upstream connections.
    """
    log.warning("resources.subscribe_push_pooling_dependent")
    return rpc_result(rpc_id, {})
