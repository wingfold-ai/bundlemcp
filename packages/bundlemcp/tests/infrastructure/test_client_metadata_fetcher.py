"""Client metadata document fetching (spec 20: OAS-13) against an httpx MockTransport."""

import httpx
import pytest
from bundlemcp.application.errors import InvalidInputError
from bundlemcp.domain.oauth.grant_type import GrantType
from bundlemcp.infrastructure.config.settings import EnvSettings
from bundlemcp.infrastructure.httpx import client_metadata_fetcher
from bundlemcp.infrastructure.httpx.client_metadata_fetcher import HttpxClientMetadataFetcher
from fakeredis.aioredis import FakeRedis

CIMD_URL = "https://client.example/oauth/client.json"


@pytest.fixture(autouse=True)
def no_dns(monkeypatch):
    """The egress policy resolves the host; these tests stay off the network."""
    monkeypatch.setattr(client_metadata_fetcher, "check_url_allowed", lambda url, settings: None)


def fetcher(handler) -> HttpxClientMetadataFetcher:
    return HttpxClientMetadataFetcher(
        EnvSettings(_env_file=None),
        FakeRedis(),
        client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


async def test_document_with_an_unimplemented_grant_is_accepted():
    """OAS-13: a grant the gateway does not issue is dropped, not a reason to refuse."""
    body = {
        "client_id": CIMD_URL,
        "redirect_uris": ["https://client.example/cb"],
        "grant_types": ["authorization_code", "urn:ietf:params:oauth:grant-type:jwt-bearer"],
        "token_endpoint_auth_method": "none",
    }
    document = await fetcher(lambda request: httpx.Response(200, json=body)).fetch(CIMD_URL)
    assert document.grant_types == [GrantType.AUTHORIZATION_CODE]


async def test_document_that_does_not_parse_is_reported_as_invalid():
    """OAS-13: a document that arrived but fails validation is not a fetch failure."""
    body = {"client_id": CIMD_URL, "redirect_uris": []}
    with pytest.raises(InvalidInputError, match="is invalid"):
        await fetcher(lambda request: httpx.Response(200, json=body)).fetch(CIMD_URL)


@pytest.mark.parametrize(
    "response",
    [httpx.Response(404), httpx.Response(200, text="not json")],
)
async def test_document_that_cannot_be_retrieved_is_reported_as_unfetchable(response):
    """OAS-13: an HTTP error or a non-JSON body means there is no document to judge."""
    with pytest.raises(InvalidInputError, match="could not be fetched"):
        await fetcher(lambda request: response).fetch(CIMD_URL)
