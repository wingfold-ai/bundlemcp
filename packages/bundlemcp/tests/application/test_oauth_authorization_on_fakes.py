"""The authorization endpoint's collaborators, run on the in-memory fakes (spec 20)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from bundlemcp.application.errors import InvalidInputError
from bundlemcp.application.oauth_server import (
    AuthorizationCodeIssuer,
    ClientResolver,
    ConsentService,
    MetadataDocumentClientSource,
    PendingAuthorization,
    RegisteredClientSource,
)
from bundlemcp.domain.oauth.client_id_metadata_document import ClientIdMetadataDocument
from bundlemcp.domain.oauth.oauth_client import OAuthClient
from bundlemcp.domain.oauth.token_policy import TokenPolicy
from bundlemcp.domain.shared.secrets import hash_token
from bundlemcp.domain.shared.sha256_secret_hasher import Sha256SecretHasher
from bundlemcp.infrastructure.memory.in_memory_unit_of_work import InMemoryUnitOfWork
from bundlemcp.infrastructure.memory.manual_clock import ManualClock
from bundlemcp.infrastructure.memory.sequential_secret_generator import (
    SequentialSecretGenerator,
)

CIMD_URL = "https://client.example/oauth/client.json"


class FakeFetcher:
    def __init__(self, document: ClientIdMetadataDocument | None) -> None:
        self._document = document
        self.fetches = 0

    async def fetch(self, client_id_url: str) -> ClientIdMetadataDocument:
        self.fetches += 1
        if self._document is None:
            raise InvalidInputError("client metadata document could not be fetched")
        return self._document


@pytest.fixture
def uow() -> InMemoryUnitOfWork:
    return InMemoryUnitOfWork()


def _resolver(uow: InMemoryUnitOfWork, fetcher: FakeFetcher) -> ClientResolver:
    return ClientResolver(
        (
            RegisteredClientSource(uow.oauth_clients),
            MetadataDocumentClientSource(uow.oauth_clients, fetcher),
        )
    )


async def test_opaque_ids_come_from_the_registry_without_a_fetch(uow):
    """OAS-2: the registry answers a registered client; the document source is never asked."""
    uow.oauth_clients.add(OAuthClient(client_id="bmcp_client_x", client_name="Reg"))
    fetcher = FakeFetcher(None)
    client = await _resolver(uow, fetcher).resolve("bmcp_client_x")
    assert client is not None and client.client_name == "Reg"
    assert fetcher.fetches == 0
    assert await _resolver(uow, fetcher).resolve("bmcp_client_unknown") is None


async def test_url_ids_are_fetched_checked_and_mirrored(uow):
    """OAS-13: a URL client_id resolves through its document and is mirrored as a client."""
    fetcher = FakeFetcher(
        ClientIdMetadataDocument(
            client_id=CIMD_URL, client_name="Docs", redirect_uris=["https://client.example/cb"]
        )
    )
    client = await _resolver(uow, fetcher).resolve(CIMD_URL)
    assert client is not None and client.is_public and client.client_name == "Docs"
    assert await uow.oauth_clients.get(CIMD_URL) is not None
    assert fetcher.fetches == 1


async def test_a_document_naming_another_url_is_refused(uow):
    """OAS-13: the document's client_id must be the URL it was fetched from."""
    fetcher = FakeFetcher(
        ClientIdMetadataDocument(
            client_id="https://elsewhere.example/c.json", redirect_uris=["https://c/cb"]
        )
    )
    with pytest.raises(InvalidInputError, match="does not name its own URL"):
        await _resolver(uow, fetcher).resolve(CIMD_URL)
    assert await uow.oauth_clients.get(CIMD_URL) is None


async def test_consent_is_remembered_per_user_client_and_endpoint(uow):
    """OAS-11: consent granted once is found again for the same triple only."""
    consents = ConsentService(uow)
    user, endpoint, other = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    assert not await consents.is_granted(user, "c", endpoint)
    await consents.grant(user, "c", endpoint)
    assert await consents.is_granted(user, "c", endpoint)
    assert not await consents.is_granted(user, "c", other)
    assert uow.committed == 1


async def test_issued_code_is_stored_as_a_hash_bound_to_the_request(uow):
    """OAS-3/OAS-8: only the hash is stored, and the code carries the request it approves."""
    pending = PendingAuthorization(
        client_id="c",
        client_name="C",
        redirect_uri="https://client.example/cb",
        scope="mcp",
        code_challenge="ch",
        endpoint_id=uuid.uuid4(),
        endpoint_name="ep1",
        bundle_name="b",
        user_id=uuid.uuid4(),
    )
    clock = ManualClock(datetime(2026, 9, 17, 12, 0, tzinfo=UTC))
    issuer = AuthorizationCodeIssuer(
        uow,
        TokenPolicy(),
        clock=clock,
        generator=SequentialSecretGenerator(),
        hasher=Sha256SecretHasher(),
    )
    raw = issuer.issue(pending)
    assert raw == "secret-1"  # the generator, not the OS, decided the value
    stored = await uow.authorization_codes.get(hash_token(raw))
    assert stored is not None and stored.is_redeemable_at(clock.now())
    assert stored.expires_at == clock.now() + timedelta(minutes=10)
    assert not stored.is_redeemable_at(clock.now() + timedelta(minutes=11))
    assert stored.client_id == "c" and stored.endpoint_id == pending.endpoint_id
    assert await uow.authorization_codes.get(raw) is None  # never the raw value
