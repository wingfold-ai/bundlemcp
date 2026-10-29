"""Client metadata document fetching (AUTH-13) against an httpx MockTransport."""

import asyncio
import json

import httpx
import pytest
from bundlemcp.application.errors import InvalidInputError
from bundlemcp.domain.oauth.grant_type import GrantType
from bundlemcp.infrastructure.config.settings import EnvSettings
from bundlemcp.infrastructure.egress.egress_policy import check_url_allowed
from bundlemcp.infrastructure.httpx import client_metadata_fetcher
from bundlemcp.infrastructure.httpx.client_metadata_fetcher import HttpxClientMetadataFetcher
from fakeredis.aioredis import FakeRedis

CIMD_URL = "https://client.example/oauth/client.json"


@pytest.fixture(autouse=True)
def no_dns(monkeypatch):
    """The egress policy resolves the host; these tests stay off the network."""
    monkeypatch.setattr(client_metadata_fetcher, "check_url_allowed", lambda *args: None)


def fetcher(handler) -> HttpxClientMetadataFetcher:
    return HttpxClientMetadataFetcher(
        EnvSettings(_env_file=None),
        FakeRedis(),
        client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


async def test_document_with_an_unimplemented_grant_is_accepted():
    """AUTH-13: a grant the gateway does not issue is dropped, not a reason to refuse."""
    body = {
        "client_id": CIMD_URL,
        "redirect_uris": ["https://client.example/cb"],
        "grant_types": ["authorization_code", "urn:ietf:params:oauth:grant-type:jwt-bearer"],
        "token_endpoint_auth_method": "none",
    }
    document = await fetcher(lambda request: httpx.Response(200, json=body)).fetch(CIMD_URL)
    assert document.grant_types == [GrantType.AUTHORIZATION_CODE]


async def test_document_that_does_not_parse_is_reported_as_invalid():
    """AUTH-13: a document that arrived but fails validation is not a fetch failure."""
    body = {"client_id": CIMD_URL, "redirect_uris": []}
    with pytest.raises(InvalidInputError, match="is invalid"):
        await fetcher(lambda request: httpx.Response(200, json=body)).fetch(CIMD_URL)


@pytest.mark.parametrize(
    "response",
    [httpx.Response(404), httpx.Response(200, text="not json")],
)
async def test_document_that_cannot_be_retrieved_is_reported_as_unfetchable(response):
    """AUTH-13: an HTTP error or a non-JSON body means there is no document to judge."""
    with pytest.raises(InvalidInputError, match="could not be fetched"):
        await fetcher(lambda request: response).fetch(CIMD_URL)


VALID = {
    "client_id": CIMD_URL,
    "redirect_uris": ["https://client.example/cb"],
    "token_endpoint_auth_method": "none",
}


class Counting:
    """A handler that answers with ``response`` and counts the requests it saw."""

    def __init__(self, response) -> None:
        self.response = response
        self.requests = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests += 1
        return self.response() if callable(self.response) else self.response


async def test_auth13_private_address_not_fetched(monkeypatch):
    """AUTH-13: a document URL on a private address is refused before any request is made."""
    monkeypatch.setattr(client_metadata_fetcher, "check_url_allowed", check_url_allowed)
    handler = Counting(httpx.Response(200, json=VALID))
    with pytest.raises(InvalidInputError, match="could not be fetched"):
        await fetcher(handler).fetch("https://10.0.0.5/client.json")
    assert handler.requests == 0


@pytest.mark.parametrize("declared", [True, False], ids=["content-length", "streamed"])
async def test_auth13_oversized_document_refused(declared):
    """AUTH-13: a body over the cap is refused, whether its length is declared or streamed."""
    padding = "x" * (client_metadata_fetcher.MAX_DOCUMENT_BYTES + 1)
    body = json.dumps({**VALID, "client_name": padding}).encode()

    async def chunks():
        for start in range(0, len(body), 1024):
            yield body[start : start + 1024]

    response = httpx.Response(200, content=body if declared else chunks())
    with pytest.raises(InvalidInputError, match="could not be fetched"):
        await fetcher(lambda request: response).fetch(CIMD_URL)


async def test_auth13_slow_document_cut_off(monkeypatch):
    """AUTH-13: a document still arriving at the deadline is abandoned."""
    monkeypatch.setattr(client_metadata_fetcher, "FETCH_DEADLINE", 0.2)

    async def trickle():
        yield b"{"
        await asyncio.sleep(5)
        yield b"}"

    with pytest.raises(InvalidInputError, match="could not be fetched"):
        await fetcher(lambda request: httpx.Response(200, content=trickle())).fetch(CIMD_URL)


async def test_auth13_failed_fetch_not_repeated():
    """AUTH-13: within a minute of a failure the same URL is refused without a new request."""
    handler = Counting(lambda: httpx.Response(404))
    cimd = fetcher(handler)
    for _ in range(3):
        with pytest.raises(InvalidInputError, match="could not be fetched"):
            await cimd.fetch(CIMD_URL)
    assert handler.requests == 1


async def test_auth13_cached_failure_keeps_its_kind():
    """AUTH-13: a remembered invalid document is still reported as invalid, not unreachable."""
    handler = Counting(lambda: httpx.Response(200, json={"client_id": CIMD_URL}))
    cimd = fetcher(handler)
    for _ in range(2):
        with pytest.raises(InvalidInputError, match="is invalid"):
            await cimd.fetch(CIMD_URL)
    assert handler.requests == 1
