import importlib
import uuid

import structlog

from bundlemcp.gateway.metering.metering_hook import MeteringHook
from bundlemcp.gateway.metering.noop_metering_hook import NoopMeteringHook

log = structlog.get_logger("bundlemcp.gateway.metering")


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
