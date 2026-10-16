"""Every logger in the process, stdlib ones included, writes the configured line format (OPS-8)."""

import json
import logging

import structlog
from bundlemcp.infrastructure.config.structured_logging import configure_logging


def test_stdlib_and_structlog_records_share_the_json_format(capsys):
    configure_logging("INFO", "json")
    logging.getLogger("uvicorn.error").info("Application startup complete.")
    structlog.get_logger("bundlemcp.test").warning("event.name", key="value")
    logging.getLogger("bundlemcp.quiet").debug("below the level")

    lines = [json.loads(line) for line in capsys.readouterr().err.strip().splitlines()]
    assert [line["logger"] for line in lines] == ["uvicorn.error", "bundlemcp.test"]
    assert lines[0]["level"] == "info" and lines[0]["event"] == "Application startup complete."
    assert lines[1]["level"] == "warning" and lines[1]["key"] == "value"
    assert all("timestamp" in line for line in lines)


def test_text_format_is_for_terminals(capsys):
    configure_logging("DEBUG", "text")
    logging.getLogger("uvicorn.error").info("started")
    out = capsys.readouterr().err
    assert "started" in out and not out.lstrip().startswith("{")


def test_ops8_logs_written_to_stderr(capsys):
    """OPS-8: every line goes to standard error, nothing to standard output."""
    configure_logging("INFO", "json")
    structlog.get_logger("bundlemcp.test").info("event.name")
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err.strip())["event"] == "event.name"


def test_ops8_uvicorn_access_lines_are_replaced(capsys):
    """OPS-8: uvicorn's access line, whose client is the proxy, is not written."""
    configure_logging("INFO", "json")
    logging.getLogger("uvicorn.access").info('GET /healthz "200"')
    assert capsys.readouterr().err == ""
