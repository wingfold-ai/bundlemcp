"""Every logger in the process, stdlib ones included, writes the configured line format (OPS-8)."""

import json
import logging

import structlog
from bundlemcp.infrastructure.config.structured_logging import configure_logging


def test_stdlib_and_structlog_records_share_the_json_format(capsys):
    configure_logging("INFO", "json")
    logging.getLogger("uvicorn.access").info('GET /healthz "200"')
    structlog.get_logger("bundlemcp.test").warning("event.name", key="value")
    logging.getLogger("bundlemcp.quiet").debug("below the level")

    lines = [json.loads(line) for line in capsys.readouterr().err.strip().splitlines()]
    assert [line["logger"] for line in lines] == ["uvicorn.access", "bundlemcp.test"]
    assert lines[0]["level"] == "info" and lines[0]["event"] == 'GET /healthz "200"'
    assert lines[1]["level"] == "warning" and lines[1]["key"] == "value"
    assert all("timestamp" in line for line in lines)


def test_text_format_is_for_terminals(capsys):
    configure_logging("DEBUG", "text")
    logging.getLogger("uvicorn.error").info("started")
    out = capsys.readouterr().err
    assert "started" in out and not out.lstrip().startswith("{")
