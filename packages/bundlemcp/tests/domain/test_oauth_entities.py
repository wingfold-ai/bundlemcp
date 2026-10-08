"""Rules the OAuth entities decide for themselves (spec 20: OAS-2, OAS-3, OAS-4, OAS-11, OAS-13)."""

import uuid
from datetime import timedelta

import pytest
from bundlemcp.domain.oauth.client_id_metadata_document import (
    ClientIdMetadataDocument,
    InvalidClientMetadataDocument,
)
from bundlemcp.domain.oauth.grant_type import GrantType
from bundlemcp.domain.oauth.oauth_authorization_code import OAuthAuthorizationCode
from bundlemcp.domain.oauth.oauth_client import OAuthClient
from bundlemcp.domain.oauth.oauth_consent import OAuthConsent
from bundlemcp.domain.oauth.pkce import PkcePair
from bundlemcp.domain.oauth.redirect_uri_allow_list import RedirectUriAllowList
from bundlemcp.domain.oauth.redirect_uri_pattern import RedirectUriPattern
from bundlemcp.domain.oauth.registration_policy import RegistrationPolicy
from bundlemcp.domain.oauth.token_endpoint_auth_method import TokenEndpointAuthMethod
from bundlemcp.domain.shared.clock import utcnow
from bundlemcp.domain.shared.sha256_secret_hasher import Sha256SecretHasher

CIMD_URL = "https://client.example/oauth/client.json"
HASHER = Sha256SecretHasher()
OPEN = RedirectUriAllowList()
CLAUDE_CALLBACK = "https://claude.ai/api/mcp/auth_callback"


def test_public_client_has_no_secret_to_verify():
    """OAS-2: a public client passes on PKCE alone and can never match a secret."""
    client = OAuthClient(client_id="c")
    assert client.is_public
    assert not client.verifies_secret("anything", HASHER)


def test_confidential_client_verifies_only_its_own_secret():
    """OAS-4: the presented secret is compared by hash; a missing one never matches."""
    client = OAuthClient(
        client_id="c",
        client_secret_hash=HASHER.digest("s3cret"),
        token_endpoint_auth_method=TokenEndpointAuthMethod.CLIENT_SECRET_POST,
    )
    assert not client.is_public
    assert client.verifies_secret("s3cret", HASHER)
    assert not client.verifies_secret("wrong", HASHER)
    assert not client.verifies_secret(None, HASHER)


def test_client_allows_only_the_grants_it_registered():
    """OAS-4: the registered grant list is what the token endpoint honours."""
    client = OAuthClient(client_id="c", grant_types=[GrantType.AUTHORIZATION_CODE])
    assert client.allows_grant(GrantType.AUTHORIZATION_CODE)
    assert not client.allows_grant(GrantType.REFRESH_TOKEN)


def test_applying_a_metadata_document_keeps_what_the_gateway_recorded():
    """OAS-13: the document replaces what the client publishes, never the gateway's own facts."""
    created = utcnow() - timedelta(days=3)
    client = OAuthClient(client_id=CIMD_URL, created_at=created, last_used_at=created)
    document = ClientIdMetadataDocument(
        client_id=CIMD_URL, client_name="Docs", redirect_uris=["https://client.example/cb"]
    )
    client.apply_metadata_document(document)
    assert client.client_name == "Docs"
    assert client.redirect_uris == ["https://client.example/cb"]
    assert client.scope == "mcp"
    assert client.created_at == created and client.last_used_at == created


@pytest.mark.parametrize(
    ("document", "reason"),
    [
        (
            ClientIdMetadataDocument(
                client_id="https://elsewhere.example/c.json", redirect_uris=["https://c/cb"]
            ),
            "does not name its own URL",
        ),
        (
            ClientIdMetadataDocument(
                client_id=CIMD_URL,
                redirect_uris=["https://c/cb"],
                token_endpoint_auth_method=TokenEndpointAuthMethod.CLIENT_SECRET_BASIC,
            ),
            "only describe public clients",
        ),
        (
            ClientIdMetadataDocument(client_id=CIMD_URL, redirect_uris=["http://c.example/cb"]),
            "invalid_redirect_uri",
        ),
    ],
)
def test_metadata_document_check_names_what_is_wrong(document, reason):
    """OAS-13: a document is refused for its URL, its auth method, or a redirect URI."""
    with pytest.raises(InvalidClientMetadataDocument, match=reason):
        document.check(fetched_from=CIMD_URL, allowed=OPEN)


def test_metadata_document_ignores_grant_types_the_gateway_does_not_implement():
    """OAS-13: Claude's published document lists jwt-bearer beside the two grants we issue."""
    claude_url = "https://claude.ai/oauth/mcp-oauth-client-metadata"
    document = ClientIdMetadataDocument.model_validate(
        {
            "client_id": claude_url,
            "client_name": "Claude",
            "client_uri": "https://claude.ai",
            "redirect_uris": ["https://claude.ai/api/mcp/auth_callback"],
            "grant_types": [
                "authorization_code",
                "refresh_token",
                "urn:ietf:params:oauth:grant-type:jwt-bearer",
            ],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
        }
    )
    assert document.grant_types == [GrantType.AUTHORIZATION_CODE, GrantType.REFRESH_TOKEN]
    document.check(fetched_from=claude_url, allowed=OPEN)


def test_metadata_document_of_only_unknown_grants_leaves_no_code_grant():
    """OAS-4/OAS-13: nothing usable is left, so the authorize endpoint refuses the client."""
    document = ClientIdMetadataDocument(
        client_id=CIMD_URL,
        redirect_uris=["https://client.example/cb"],
        grant_types=["urn:ietf:params:oauth:grant-type:jwt-bearer"],
    )
    client = OAuthClient(client_id=CIMD_URL)
    client.apply_metadata_document(document)
    assert not client.allows_grant(GrantType.AUTHORIZATION_CODE)


def _code(pkce: PkcePair) -> OAuthAuthorizationCode:
    return OAuthAuthorizationCode(
        code_hash="h",
        client_id="c",
        user_id=uuid.uuid4(),
        endpoint_id=uuid.uuid4(),
        redirect_uri="https://client.example/cb",
        code_challenge=pkce.challenge,
        expires_at=utcnow() + timedelta(minutes=5),
    )


def test_code_binds_client_redirect_and_verifier():
    """OAS-3: a code is bound to its client, its redirect URI and its PKCE challenge."""
    pkce = PkcePair.generate()
    code = _code(pkce)
    assert code.issued_to("c") and not code.issued_to("other")
    assert code.sent_to("https://client.example/cb") and not code.sent_to(None)
    assert code.proves_possession(pkce.verifier)
    assert not code.proves_possession(PkcePair.generate().verifier)


def test_consent_stands_until_revoked():
    """OAS-11: an active consent skips the screen; a revoked one does not."""
    consent = OAuthConsent(user_id=uuid.uuid4(), client_id="c", endpoint_id=uuid.uuid4())
    assert consent.is_active
    consent.revoke(utcnow())
    assert not consent.is_active


def test_metadata_document_redirect_uris_must_be_on_a_configured_allow_list():
    """OAS-13: a configured allow-list narrows the redirect URIs a document may declare."""
    document = ClientIdMetadataDocument(
        client_id=CIMD_URL, redirect_uris=["https://client.example/cb"]
    )
    document.check(fetched_from=CIMD_URL, allowed=RedirectUriAllowList.of(["https://client.example/cb"]))
    with pytest.raises(InvalidClientMetadataDocument, match="invalid_redirect_uri"):
        document.check(
            fetched_from=CIMD_URL, allowed=RedirectUriAllowList.of(["https://claude.ai/cb"])
        )


@pytest.mark.parametrize(
    ("pattern", "uri", "expected"),
    [
        (CLAUDE_CALLBACK, CLAUDE_CALLBACK, True),
        (CLAUDE_CALLBACK, f"{CLAUDE_CALLBACK}/", False),
        (CLAUDE_CALLBACK, "https://CLAUDE.ai/api/mcp/auth_callback", False),
        ("https://*.example.com/cb", "https://app.example.com/cb", True),
        ("https://*.example.com/cb", "https://APP.example.com/cb", True),
        ("https://*.example.com/cb", "https://example.com/cb", False),
        ("https://*.example.com/cb", "https://a.b.example.com/cb", False),
        ("https://*.example.com/cb", "https://app.example.com/cb?x=1", False),
        ("https://*.example.com/cb", "https://app.example.com:8443/cb", False),
        ("https://*.example.com/cb", "http://app.example.com/cb", False),
        ("https://*.example.com/cb", "https://app.example.com/cb/other", False),
        ("https://*.example.com/cb", "https://app.example.com@evil.com/cb", False),
        ("https://*.example.com/cb", "https://user@app.example.com/cb", False),
        ("https://*.example.com/cb", "https://app.example.com.evil.com/cb", False),
        ("https://*.example.com/cb", "https://x%2F.example.com/cb", False),
        ("https://*.example.com:8443/cb", "https://app.example.com:8443/cb", True),
    ],
)
def test_redirect_uri_pattern_matches_exact_uris_and_one_wildcard_label(pattern, uri, expected):
    """OAS-2: an exact entry compares strings; a wildcard stands for exactly one host label."""
    assert RedirectUriPattern(pattern=pattern).matches(uri) is expected


@pytest.mark.parametrize(
    "bad",
    [
        "claude.ai/cb",
        "ftp://claude.ai/cb",
        "https://*.com/cb",
        "https://a.*.example.com/cb",
        "https://*x.example.com/cb",
        "https://*.example.com/*",
        "https://claude.ai/cb#frag",
        "https://user@claude.ai/cb",
        "https://claude.ai:notaport/cb",
    ],
)
def test_redirect_uri_pattern_refuses_malformed_entries(bad):
    """OAS-2: only exact URIs and a whole leftmost wildcard label are valid entries."""
    with pytest.raises(ValueError):
        RedirectUriPattern(pattern=bad)


def test_empty_allow_list_permits_everything_and_vouches_for_nothing():
    """OAS-2/OAS-12: no list keeps today's acceptance and exempts nobody from the IP limit."""
    assert OPEN.permits("https://evil.example/cb")
    assert not OPEN.vouches_for(["https://evil.example/cb"])


def test_allow_list_vouches_only_when_every_uri_is_listed():
    """OAS-12: one unlisted redirect URI keeps the registration under the per-IP limit."""
    allowed = RedirectUriAllowList.of(["https://claude.ai/cb"])
    assert allowed.vouches_for(["https://claude.ai/cb"])
    assert not allowed.vouches_for(["https://claude.ai/cb", "https://evil.example/cb"])
    assert not allowed.vouches_for([])
    assert not allowed.permits("https://evil.example/cb")


def test_registration_policy_exempts_listed_uris_and_caps_unused_clients():
    """OAS-12/SEC-8: the per-IP limit spares listed URIs; the unused-client cap spares none."""
    policy = RegistrationPolicy(
        allowed_redirect_uris=RedirectUriAllowList.of(["https://claude.ai/cb"]),
        per_ip_limit=10,
        per_ip_window=3600,
        max_unused_clients=2,
    )
    assert not policy.limits_per_ip(["https://claude.ai/cb"])
    assert policy.limits_per_ip(["https://other.example/cb"])
    assert policy.admits_another(1)
    assert not policy.admits_another(2)
