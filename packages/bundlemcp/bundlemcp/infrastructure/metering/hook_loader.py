"""Resolving the configured metering hook at startup."""

import importlib

import structlog

from bundlemcp.application.metering.metering_hook import MeteringHook
from bundlemcp.application.settings.settings import Settings
from bundlemcp.infrastructure.memory.noop_metering_hook import NoopMeteringHook
from bundlemcp.infrastructure.metering.http_metering_hook import HttpMeteringHook

log = structlog.get_logger("bundlemcp.infrastructure.metering")


def load_metering_hook(settings: Settings) -> MeteringHook:
    """The billing service over HTTP, an in-process hook, or a no-op when neither is set."""
    if settings.metering_http_url:  # MID-6
        log.info("metering.http_hook")  # the URL may carry credentials; not logged
        return HttpMeteringHook(
            settings.metering_http_url,
            token=settings.metering_http_token,
            timeout=settings.metering_http_timeout,
        )
    return _import_hook(settings.metering_hook)


def _import_hook(import_path: str | None) -> MeteringHook:
    """Load from BUNDLEMCP_METERING_HOOK='package.module:attribute' (instance or factory)."""
    if not import_path:
        return NoopMeteringHook()
    module_name, _, attr = import_path.partition(":")
    obj = getattr(importlib.import_module(module_name), attr)
    hook = obj() if callable(obj) and not hasattr(obj, "pre_call") else obj
    log.info("metering.hook_loaded", path=import_path)
    return hook
