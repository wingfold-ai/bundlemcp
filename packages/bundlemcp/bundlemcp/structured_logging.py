"""Structured logging for everything the process writes: structlog and stdlib alike.

Uvicorn, SQLAlchemy and other libraries log through the standard library.
Routing their records through the same structlog formatter keeps production
stdout to one line format, so a log pipeline never meets a plain-text access
log beside JSON application events.
"""

import logging

import structlog

FOREIGN_LOGGERS = ("uvicorn", "uvicorn.access", "uvicorn.error")


def configure_logging(level: str, log_format: str = "json") -> None:
    """Send every log record to stdout in the chosen format, at the given minimum level.

    Safe to call more than once; each call replaces the previous handler.
    """
    shared_processors: list[structlog.typing.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
    ]
    renderer: structlog.typing.Processor = (
        structlog.processors.JSONRenderer()
        if log_format == "json"
        else structlog.dev.ConsoleRenderer()
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
