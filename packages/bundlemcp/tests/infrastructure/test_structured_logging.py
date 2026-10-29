"""Every logger in the process, stdlib ones included, writes the configured line format (OPS-8)."""

import json
import logging
import uuid

import structlog
from bundlemcp.infrastructure.config.structured_logging import configure_logging
from bundlemcp.infrastructure.postgres.engine import session_factory
from bundlemcp.infrastructure.postgres.rows.upstream_oauth_token_row import UpstreamOAuthTokenRow
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.exc import IntegrityError

from tests.redaction import assert_redacted


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


TOKEN = "tok_live_9f8e7d6c5b4a"


def _fail_holding_a_token() -> None:
    secret_token = TOKEN  # noqa: F841 - the local a rendered traceback must never show
    raise RuntimeError("upstream refused the call")


def _log_failure(event: str) -> None:
    try:
        _fail_holding_a_token()
    except RuntimeError:
        structlog.get_logger("bundlemcp.test").warning(event, exc_info=True)


def test_ops8_logged_exception_carries_its_traceback(capsys):
    """OPS-8: in json, a line logged with its exception is one object whose ``exception`` field
    names the type, the message and the frames it passed through."""
    configure_logging("INFO", "json")
    _log_failure("call.failed")
    (line,) = capsys.readouterr().err.strip().splitlines()
    event = json.loads(line)
    assert "exc_info" not in event
    assert event["exception"].startswith("Traceback (most recent call last):")
    assert "RuntimeError: upstream refused the call" in event["exception"]
    assert "_fail_holding_a_token" in event["exception"]


def test_ops8_a_chained_cause_is_rendered_first(capsys):
    """OPS-8: an exception raised from another carries both, the cause first, as the standard
    library prints them."""
    configure_logging("INFO", "json")
    try:
        try:
            raise KeyError("missing")
        except KeyError as exc:
            raise LookupError("not found") from exc
    except LookupError:
        structlog.get_logger("bundlemcp.test").warning("lookup.failed", exc_info=True)
    rendered = json.loads(capsys.readouterr().err)["exception"]
    assert rendered.index("KeyError: 'missing'") < rendered.index("direct cause")
    assert rendered.index("direct cause") < rendered.index("LookupError: not found")


def test_ops8_traceback_never_shows_locals(capsys):
    """OPS-8, SEC-10: neither format renders a frame's local variables, so a token held in one
    stays out of the log, whether logged through structlog or the standard library."""
    for log_format in ("json", "text"):
        configure_logging("INFO", log_format)
        _log_failure("call.failed")
        try:
            _fail_holding_a_token()
        except RuntimeError:
            logging.getLogger("bundlemcp.stdlib").exception("stdlib.failed")
        out = capsys.readouterr().err
        assert "upstream refused the call" in out
        assert_redacted(out, [TOKEN])


def test_sec10_validation_error_input_is_not_logged(capsys):
    """SEC-10, OPS-8: a validation error over a secret-bearing value is logged with its location
    and reason, but not with the value it rejected."""

    class Credentials(BaseModel):
        port: int = Field(description="A port that a secret was wrongly sent for")

    for log_format in ("json", "text"):
        configure_logging("INFO", log_format)
        try:
            Credentials.model_validate({"port": TOKEN})
        except ValidationError:
            structlog.get_logger("bundlemcp.test").warning("config.invalid", exc_info=True)
        out = capsys.readouterr().err
        assert "1 validation error for Credentials" in out
        assert "port: Input should be a valid integer" in out
        assert_redacted(out, [TOKEN])


async def test_sec10_database_errors_hide_statement_parameters(engine, capsys):
    """SEC-10, OPS-8: a failed statement logged with its exception names the statement, but
    not the ciphertext among its bound parameters."""
    ciphertext = "gAAAAABciphertext-that-must-not-be-logged"
    configure_logging("INFO", "json")
    async with session_factory(engine)() as db:
        db.add(UpstreamOAuthTokenRow(server_id=uuid.uuid4(), tokens_encrypted=ciphertext))
        try:
            await db.commit()
        except IntegrityError:
            structlog.get_logger("bundlemcp.test").warning("token.save_failed", exc_info=True)
    rendered = json.loads(capsys.readouterr().err.strip().splitlines()[-1])["exception"]
    assert "IntegrityError" in rendered
    assert "SQL parameters hidden" in rendered
    assert_redacted(rendered, [ciphertext])
