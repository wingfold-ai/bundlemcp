"""Whether to trace, decided once from the standard OpenTelemetry variables."""

import os
from collections.abc import Mapping
from typing import Any

import structlog
from fastapi import FastAPI

log = structlog.get_logger(__name__)

EXPORTER_VARIABLES = ("OTEL_EXPORTER_OTLP_ENDPOINT", "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")


def tracing_requested(environ: Mapping[str, str] = os.environ) -> bool:
    """An exporter endpoint is configured and the SDK is not switched off."""
    if environ.get("OTEL_SDK_DISABLED", "").strip().lower() == "true":
        return False
    return any(environ.get(name) for name in EXPORTER_VARIABLES)


def start_tracing(app: FastAPI, *, processor: Any = None) -> Any:
    """The configured tracing for ``app``, or None when the tracing extra is not installed.

    Nothing from the OpenTelemetry SDK is imported unless this is called, so a
    gateway without an exporter configured loads none of it.
    """
    try:
        from bundlemcp.infrastructure.opentelemetry.tracing import Tracing  # noqa: PLC0415
    except ImportError:
        log.warning(
            "tracing.extra_missing",
            hint="install bundlemcp[otel] (or build the image with the otel extra) to trace",
        )
        return None
    return Tracing(app, processor=processor)
