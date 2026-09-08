"""Resolving the configured metering hook at startup."""

import importlib

import structlog

from bundlemcp.application.metering.metering_hook import MeteringHook
from bundlemcp.infrastructure.memory.noop_metering_hook import NoopMeteringHook

log = structlog.get_logger("bundlemcp.infrastructure.metering")


def load_metering_hook(import_path: str | None) -> MeteringHook:
    """Load from BUNDLEMCP_METERING_HOOK='package.module:attribute' (instance or factory)."""
    if not import_path:
        return NoopMeteringHook()
    module_name, _, attr = import_path.partition(":")
    obj = getattr(importlib.import_module(module_name), attr)
    hook = obj() if callable(obj) and not hasattr(obj, "pre_call") else obj
    log.info("metering.hook_loaded", path=import_path)
    return hook
