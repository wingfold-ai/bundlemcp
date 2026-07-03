"""Metering hook contract: the application layer's extension point.

The protocol below is versioned and semver-relevant. ultra-mcp field
mapping: sub->sub, email->email, bundle->bundle_slug, server->server_name,
tool->tool_name, idempotency_key->idempotency_key; `endpoint` is
bundlemcp-side context the reference consumer ignores.
"""

import importlib
import uuid
from dataclasses import dataclass
from typing import Literal, Protocol

import structlog

log = structlog.get_logger(__name__)

METERING_PROTOCOL_VERSION = 1


@dataclass(frozen=True)
class MeterContext:
    sub: str | None  # user id, or "api_key:<id>", or None for anonymous
    email: str | None
    endpoint: str
    bundle: str
    server: str
    tool: str
    idempotency_key: str  # once per client invocation; internal retries reuse it


@dataclass(frozen=True)
class MeterDecision:
    allowed: bool
    reason: str | None = None  # e.g. "insufficient_credits"


class MeteringHook(Protocol):
    async def pre_call(self, ctx: MeterContext) -> MeterDecision: ...

    async def post_call(
        self, ctx: MeterContext, status: Literal["success", "error"], duration_ms: int
    ) -> None: ...


class NoopMeteringHook:
    async def pre_call(self, ctx: MeterContext) -> MeterDecision:
        return MeterDecision(allowed=True)

    async def post_call(self, ctx, status, duration_ms) -> None:
        return None


def load_metering_hook(import_path: str | None) -> MeteringHook:
    """Load from BUNDLEMCP_METERING_HOOK='package.module:attribute' (instance or factory)."""
    if not import_path:
        return NoopMeteringHook()
    module_name, _, attr = import_path.partition(":")
    obj = getattr(importlib.import_module(module_name), attr)
    hook = obj() if callable(obj) and not hasattr(obj, "pre_call") else obj
    log.info("metering.hook_loaded", path=import_path)
    return hook


def new_idempotency_key() -> str:
    return uuid.uuid4().hex
