"""Which requests one upstream session may serve (AUTH-31, SES-5, SES-6, SES-7)."""

import json

from bundlemcp.domain.servers.identity_mode import IdentityMode
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.servers.observed_response import ObservedResponse
from bundlemcp.domain.servers.response_log import ResponseLog
from bundlemcp.domain.servers.server_auth_mode import ServerAuthMode
from bundlemcp.domain.sessions.session_record import SessionRecord
from bundlemcp.domain.sessions.upstream_binding import UpstreamBinding
from bundlemcp.domain.sessions.upstream_failure import UpstreamFailure
from bundlemcp.domain.sessions.upstream_retry_policy import UpstreamRetryPolicy
from bundlemcp.domain.sessions.upstream_session_key import UpstreamSessionKey

FORWARDING = McpServer(
    name="crm", url="https://crm.example/mcp", forward_headers={"authorization": "authorization"}
)
FREE = McpServer(name="echo", url="https://echo.example/mcp", send_identity_header=False)


def _key(server: McpServer, sub: str = "alice", **headers: str) -> UpstreamSessionKey:
    return UpstreamSessionKey.for_request(
        server, sub=sub, forwarded_headers=headers, endpoint="main"
    )


def test_auth31_same_user_with_two_credentials_gets_two_keys():
    """AUTH-31: the forwarded header values enter the key, not just the subject."""
    assert _key(FORWARDING, authorization="Bearer a") != _key(FORWARDING, authorization="Bearer b")


def test_auth31_matching_identity_gives_the_same_key():
    """AUTH-31: the same caller with the same headers is served by the same session."""
    assert _key(FORWARDING, authorization="Bearer a") == _key(FORWARDING, authorization="Bearer a")


def test_auth31_two_callers_never_share_a_key():
    """AUTH-31: another subject with the same header still gets its own session."""
    one = _key(FORWARDING, "alice", authorization="Bearer a")
    assert one != _key(FORWARDING, "bob", authorization="Bearer a")


def test_auth31_the_key_holds_no_header_value():
    """AUTH-31: only a digest of the forwarded headers is kept."""
    key = _key(FORWARDING, authorization="Bearer secret-value")
    assert "secret-value" not in json.dumps(key.model_dump())


def test_ses6_an_identity_free_server_is_shared():
    """SES-6: a server nothing caller-specific reaches is keyed 'shared' for every caller."""
    assert FREE.is_identity_free
    assert _key(FREE, "alice").is_shared
    assert _key(FREE, "alice") == _key(FREE, "bob")


def test_ses6_the_identity_header_makes_a_server_identity_bound():
    """SES-6: a server sent the caller's identity header is not shared between callers."""
    server = FREE.model_copy(update={"send_identity_header": True})
    assert not server.is_identity_free
    assert _key(server, "alice") != _key(server, "bob")


def test_ses6_per_user_oauth_is_keyed_by_the_caller_not_the_token():
    """SES-6: a token refresh keeps the key; the bearer is injected per request instead."""
    server = FREE.model_copy(
        update={"auth_mode": ServerAuthMode.UPSTREAM_OAUTH, "identity_mode": IdentityMode.PER_USER}
    )
    assert not server.is_identity_free
    assert _key(server, "alice") == _key(server, "alice")
    assert _key(server, "alice") != _key(server, "bob")


def test_ses6_shared_upstream_oauth_stays_identity_free():
    """SES-6: one shared upstream account serves every caller the same way."""
    server = FREE.model_copy(update={"auth_mode": ServerAuthMode.UPSTREAM_OAUTH})
    assert server.is_identity_free


def test_ses6_delegated_tokens_are_keyed_by_endpoint_too():
    """SES-6: a delegated token is minted per endpoint, so each endpoint has its own session."""
    server = FREE.model_copy(update={"auth_mode": ServerAuthMode.DELEGATED_TOKEN})
    main = UpstreamSessionKey.for_request(server, sub="a", forwarded_headers={}, endpoint="main")
    other = UpstreamSessionKey.for_request(server, sub="a", forwarded_headers={}, endpoint="ops")
    assert main != other


def test_ses9_a_config_change_changes_the_key():
    """SES-9: a session opened under the old URL or headers never matches a new request."""
    moved = FREE.model_copy(update={"url": "https://elsewhere.example/mcp"})
    retagged = FREE.model_copy(update={"static_headers": {"x-tenant": "b"}})
    assert _key(moved) != _key(FREE)
    assert _key(retagged) != _key(FREE)


def test_ses5_a_binding_continues_only_under_its_own_key():
    """SES-5: a recorded upstream session is continued only with the same config and identity."""
    key = _key(FORWARDING, authorization="Bearer a")
    binding = UpstreamBinding(
        server_name="crm",
        upstream_session_id="up-1",
        identity_key=key.identity_key,
        config_fingerprint=key.config_fingerprint,
        protocol_version="2025-11-25",
    )
    assert binding.continues(key)
    assert not binding.continues(_key(FORWARDING, authorization="Bearer b"))
    moved = FORWARDING.model_copy(update={"url": "https://crm2.example/mcp"})
    assert not binding.continues(_key(moved, authorization="Bearer a"))
    assert not binding.model_copy(update={"upstream_session_id": None}).continues(key)


def test_ses5_a_record_written_by_the_previous_build_still_loads():
    """SES-5: a version-2 binding without the new fields loads, and continues nothing."""
    stored = {
        "version": 2,
        "session_id": "s",
        "endpoint_name": "main",
        "bundle_name": "main",
        "identity": {"sub": "alice", "auth_method": "api_key"},
        "protocol_version": "2025-11-25",
        "bindings": {"crm": {"server_name": "crm", "identity_key": "alice"}},
    }
    record = SessionRecord.model_validate_json(json.dumps(stored))
    assert not record.bindings["crm"].continues(_key(FORWARDING, authorization="Bearer a"))


def test_ses7_a_tool_call_is_retried_only_when_it_cannot_have_run():
    """SES-7: a 404 or an unsent request is retried; a request lost after sending is not."""
    call = UpstreamRetryPolicy(read_only=False)
    assert call.allows_retry(UpstreamFailure.SESSION_EXPIRED, retried=False)
    assert call.allows_retry(UpstreamFailure.NOT_SENT, retried=False)
    assert not call.allows_retry(UpstreamFailure.LOST_AFTER_SEND, retried=False)
    assert not call.allows_retry(None, retried=False)


def test_ses7_a_read_is_retried_after_any_transport_loss():
    """SES-7: reading twice is harmless, so a read survives a lost connection."""
    assert UpstreamRetryPolicy(read_only=True).allows_retry(
        UpstreamFailure.LOST_AFTER_SEND, retried=False
    )


def test_ses7_nothing_is_retried_twice():
    """SES-7: one retry, whatever went wrong."""
    for read_only in (True, False):
        policy = UpstreamRetryPolicy(read_only=read_only)
        assert not policy.allows_retry(UpstreamFailure.SESSION_EXPIRED, retried=True)


def test_ses7_failures_are_classified_from_what_the_transport_saw():
    """SES-7: a 404 expired the session; an unopened connection sent nothing."""
    expired = ResponseLog()
    expired.record(ObservedResponse(status=404))
    assert UpstreamFailure.of(expired, jsonrpc_code=None) is UpstreamFailure.SESSION_EXPIRED
    unsent = ResponseLog()
    unsent.record_unsent()
    assert UpstreamFailure.of(unsent, jsonrpc_code=None) is UpstreamFailure.NOT_SENT
    dropped = ResponseLog()
    dropped.record_transport_failure()
    assert UpstreamFailure.of(dropped, jsonrpc_code=None) is UpstreamFailure.LOST_AFTER_SEND
    assert UpstreamFailure.of(ResponseLog(), jsonrpc_code=-32602) is None
