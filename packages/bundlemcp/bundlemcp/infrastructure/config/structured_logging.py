"""Structured logging for everything the process writes: structlog and stdlib alike.

Uvicorn, SQLAlchemy and other libraries log through the standard library.
Routing their records through the same structlog formatter keeps the
process's log output (standard error) to one line format, so a log pipeline
never meets a plain-text access log beside JSON application events.
"""

import logging

import structlog

from bundlemcp.infrastructure.config.traceback_renderer import TracebackRenderer

FOREIGN_LOGGERS = ("uvicorn", "uvicorn.access", "uvicorn.error")
# replaced by the gateway's own http.request line, which names the client rather than the proxy
SILENCED_LOGGERS = ("uvicorn.access",)


def _shared_processors() -> list[structlog.typing.Processor]:
    """What every log line carries, whichever handler renders it."""
    return [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        TracebackRenderer(),
    ]


def json_event_formatter() -> logging.Formatter:
    """A formatter rendering any record, structlog's or the standard library's, as the JSON line.

    A second handler with this formatter sees exactly the fields the process log
    writes, so it can never carry anything the process log may not.
    """
    return structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=_shared_processors(),
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(),
        ],
    )


def configure_logging(level: str, log_format: str = "json") -> None:
    """Send every log record to standard error in the chosen format, at the given minimum level.

    Safe to call more than once; each call replaces the previous handler.
    """
    shared_processors = _shared_processors()
    renderer: structlog.typing.Processor = (
        structlog.processors.JSONRenderer()
        if log_format == "json"
        # an exc_info that reaches the renderer unprocessed is formatted without locals
        else structlog.dev.ConsoleRenderer(exception_formatter=structlog.dev.plain_traceback)
    )
    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=False,
    )
    handler = logging.StreamHandler()
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared_processors,
            processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, renderer],
        )
    )
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(logging.getLevelNamesMapping()[level.upper()])
    for name in FOREIGN_LOGGERS:
        # uvicorn installs its own text handlers and levels before the app is
        # built; the root handler and level govern from here on
        foreign = logging.getLogger(name)
        foreign.handlers.clear()
        foreign.setLevel(logging.NOTSET)
        foreign.propagate = True
    for name in SILENCED_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
