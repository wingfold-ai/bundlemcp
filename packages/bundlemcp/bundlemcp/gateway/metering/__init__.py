"""Metering hook contract: the application layer's extension point.

The protocol below is versioned and semver-relevant. application-layer field
mapping: sub->sub, email->email, bundle->bundle_slug, server->server_name,
tool->tool_name, idempotency_key->idempotency_key; `endpoint` is
bundlemcp-side context the reference consumer ignores.
"""

from bundlemcp.gateway.metering.idempotency_key import new_idempotency_key
from bundlemcp.gateway.metering.meter_context import MeterContext
from bundlemcp.gateway.metering.meter_decision import MeterDecision
from bundlemcp.gateway.metering.metering_hook import METERING_PROTOCOL_VERSION, MeteringHook
from bundlemcp.gateway.metering.metering_hook_loader import load_metering_hook
from bundlemcp.gateway.metering.noop_metering_hook import NoopMeteringHook

__all__ = [
    "METERING_PROTOCOL_VERSION",
    "MeterContext",
    "MeterDecision",
    "MeteringHook",
    "NoopMeteringHook",
    "load_metering_hook",
    "new_idempotency_key",
]
