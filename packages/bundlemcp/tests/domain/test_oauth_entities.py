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
from bundlemcp.domain.oauth.token_endpoint_auth_method import TokenEndpointAuthMethod
from bundlemcp.domain.shared.clock import utcnow
from bundlemcp.domain.shared.secrets import hash_token

CIMD_URL = "https://client.example/oauth/client.json"


def test_public_client_has_no_secret_to_verify():
    """OAS-2: a public client passes on PKCE alone and can never match a secret."""
    client = OAuthClient(client_id="c")
    assert client.is_public
    assert not client.verifies_secret("anything")


def test_confidential_client_verifies_only_its_own_secret():
    """OAS-4: the presented secret is compared by hash; a missing one never matches."""
    client = OAuthClient(
        client_id="c",
        client_secret_hash=hash_token("s3cret"),
        token_endpoint_auth_method=TokenEndpointAuthMethod.CLIENT_SECRET_POST,
    )
    assert not client.is_public
    assert client.verifies_secret("s3cret")
    assert not client.verifies_secret("wrong")
    assert not client.verifies_secret(None)


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
        document.check(fetched_from=CIMD_URL)


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
