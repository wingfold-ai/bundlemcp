"""What an upstream's answer means, and the facts a server's configuration implies.

UPS-1, UPS-12, UPS-13, UPS-14, UPS-25, UPS-34, UPS-36, AUTH-33.
"""

import pytest
from bundlemcp.domain.servers.connection_classifier import classify_refusal
from bundlemcp.domain.servers.connection_state import ConnectionState
from bundlemcp.domain.servers.forward_header_rules import is_forwardable
from bundlemcp.domain.servers.internal_host import is_internal_host
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.servers.observed_response import ObservedResponse
from bundlemcp.domain.servers.response_log import ResponseLog
from bundlemcp.domain.servers.server_auth_mode import ServerAuthMode
from bundlemcp.domain.servers.server_name_suggestion import suggest_server_name
from bundlemcp.domain.upstream_oauth.client_identification import ClientIdentification
from bundlemcp.domain.upstream_oauth.resource_indicator import resource_indicator
from bundlemcp.domain.upstream_oauth.upstream_challenge import UpstreamChallenge
from bundlemcp.domain.upstream_oauth.upstream_metadata import UpstreamMetadata

OAUTH_CHALLENGE = (
    'Bearer error="invalid_token", '
    'resource_metadata="https://api.example/.well-known/oauth-protected-resource/mcp", '
    'scope="files:read files:write"'
)


def refusal(status: int, header: str | None = None, content_type: str = "") -> ObservedResponse:
    return ObservedResponse(
        status=status, content_type=content_type, challenge=UpstreamChallenge.parse(header)
    )


def test_a_bearer_challenge_naming_its_metadata_is_oauth():
    challenge = UpstreamChallenge.parse(OAUTH_CHALLENGE)
    assert challenge.names_oauth
    assert challenge.scope == ["files:read", "files:write"]
    assert challenge.error == "invalid_token"


def test_challenges_without_oauth_metadata_are_not_oauth():
    assert not UpstreamChallenge.parse('Bearer realm="api"').names_oauth
    assert not UpstreamChallenge.parse('Basic realm="x"').names_oauth
    assert UpstreamChallenge.parse(None) == UpstreamChallenge()


@pytest.mark.parametrize(
    ("observed", "state"),
    [
        (refusal(401, OAUTH_CHALLENGE), ConnectionState.OAUTH_REQUIRED),
        (refusal(401, 'Bearer realm="api"'), ConnectionState.CREDENTIAL_REQUIRED),
        (refusal(403), ConnectionState.CREDENTIAL_REQUIRED),
        (
            refusal(403, 'Bearer error="insufficient_scope", scope="admin"'),
            ConnectionState.INSUFFICIENT_SCOPE,
        ),
        (refusal(404, content_type="text/html"), ConnectionState.NOT_MCP),
        (refusal(405), ConnectionState.NOT_MCP),
        (refusal(200, content_type="text/html"), ConnectionState.NOT_MCP),
        (refusal(404, content_type="application/json"), ConnectionState.ERROR),
        (refusal(500), ConnectionState.ERROR),
    ],
)
def test_ups12_refusals_are_classified_from_the_http_evidence(observed, state):
    assert classify_refusal(observed, unreachable=False) == state


def test_ups12_a_401_alone_is_never_evidence_of_oauth():
    """VS Code's trap: an expired API key must not read as an OAuth prompt."""
    assert classify_refusal(refusal(401), unreachable=False) == ConnectionState.CREDENTIAL_REQUIRED


def test_ups12_no_response_at_all_is_unreachable_or_an_error():
    assert classify_refusal(None, unreachable=True) == ConnectionState.UNREACHABLE
    assert classify_refusal(None, unreachable=False) == ConnectionState.ERROR


def test_response_log_finds_the_step_up_challenge_and_the_401():
    log = ResponseLog()
    log.record(refusal(401))
    log.record(refusal(403, 'Bearer error="insufficient_scope", scope="admin"'))
    assert log.saw_unauthorized
    assert log.insufficient_scope is not None
    assert log.insufficient_scope.challenge.scope == ["admin"]


@pytest.mark.parametrize(
    ("url", "internal"),
    [
        ("http://seo-gsc:8000/mcp", True),
        ("http://localhost:9000/mcp", True),
        ("http://10.1.2.3/mcp", True),
        ("http://mcp.svc.internal/mcp", True),
        ("http://printer.local/mcp", True),
        ("http://seo.tools.svc/mcp", True),
        ("https://mcp.linear.app/mcp", False),
        ("https://8.8.8.8/mcp", False),
    ],
)
def test_ups13_internal_hosts(url, internal):
    assert is_internal_host(url) is internal


def test_ups1_none_and_static_headers_follow_the_stored_headers():
    assert ServerAuthMode.NONE.settled(has_static_headers=True) == ServerAuthMode.STATIC_HEADERS
    assert ServerAuthMode.STATIC_HEADERS.settled(has_static_headers=False) == ServerAuthMode.NONE
    oauth = ServerAuthMode.UPSTREAM_OAUTH
    assert oauth.settled(has_static_headers=True) == oauth
    delegated = ServerAuthMode.DELEGATED_TOKEN
    assert delegated.settled(has_static_headers=True) == delegated


@pytest.mark.parametrize("header", ["Cookie", "host", "X-API-Key", "Sec-Fetch-Mode", "proxy-auth"])
def test_ups14_denied_headers_are_not_forwardable(header):
    assert not is_forwardable(header)


def test_ups12_a_state_that_contradicts_the_configuration_names_the_fix():
    server = McpServer(name="s", url="https://x/mcp")
    server.connection_state = ConnectionState.OAUTH_REQUIRED
    assert "upstream OAuth" in (server.configuration_mismatch or "")
    server.connection_state = ConnectionState.CREDENTIAL_REQUIRED
    assert "header" in (server.configuration_mismatch or "")
    server.static_headers = {"authorization": "Bearer k"}
    assert server.configuration_mismatch is None  # a bad key, not a missing one


def test_auth33_forwarding_authorization_is_reported_as_passthrough():
    server = McpServer(
        name="s", url="http://x/mcp", forward_headers={"Authorization": "authorization"}
    )
    assert server.forwards_caller_token
    assert not McpServer(name="t", url="http://x/mcp").forwards_caller_token


def test_ups25_identification_prefers_a_metadata_document_then_registration():
    meta = UpstreamMetadata(
        authorization_endpoint="https://as/a",
        token_endpoint="https://as/t",
        registration_endpoint="https://as/r",
        client_id_metadata_document_supported=True,
        token_endpoint_auth_methods_supported=["none", "client_secret_basic"],
    )
    assert (
        meta.automatic_identification(metadata_document_usable=True)
        == ClientIdentification.METADATA_DOCUMENT
    )
    # a gateway not served over https cannot be fetched, so it registers instead
    assert (
        meta.automatic_identification(metadata_document_usable=False)
        == ClientIdentification.DYNAMIC_REGISTRATION
    )
    confidential_only = meta.model_copy(
        update={"token_endpoint_auth_methods_supported": ["client_secret_basic"]}
    )
    assert (
        confidential_only.automatic_identification(metadata_document_usable=True)
        == ClientIdentification.DYNAMIC_REGISTRATION
    )
    bare = meta.model_copy(
        update={"registration_endpoint": None, "client_id_metadata_document_supported": False}
    )
    assert (
        bare.automatic_identification(metadata_document_usable=True)
        == ClientIdentification.PREREGISTERED_REQUIRED
    )


def test_ups34_step_up_scopes_are_requested_with_the_resource_scopes():
    meta = UpstreamMetadata(
        authorization_endpoint="https://as/a",
        token_endpoint="https://as/t",
        resource_scopes=["files:read"],
        step_up_scopes=["files:write", "files:read"],
    )
    assert meta.authorization_scope == "files:read files:write"


def test_ups36_resource_is_the_documents_parent_identifier_or_the_url():
    url = "https://API.example/tenants/a/mcp/"
    assert resource_indicator(url, None) == "https://api.example/tenants/a/mcp"
    assert resource_indicator(url, {"resource": "https://api.example/tenants/a"}) == (
        "https://api.example/tenants/a"
    )
    # a document naming some other resource is not trusted to widen the request
    assert resource_indicator(url, {"resource": "https://evil.example"}) == (
        "https://api.example/tenants/a/mcp"
    )


@pytest.mark.parametrize(
    ("label", "url", "name"),
    [
        ("io.github.acme/Weather Server", "https://x/mcp", "weather-server"),
        (None, "https://mcp.linear.app/mcp", "linear"),
        (None, "http://seo-gsc:8000/mcp", "seo-gsc"),
        ("Bad__Name!!", "https://x", "bad-name"),
        (None, "http://127.0.0.1:8021/mcp", "server"),
    ],
)
def test_ups11_suggested_names_are_slug_safe(label, url, name):
    assert suggest_server_name(label, url) == name
