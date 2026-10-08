"""The authorization endpoint's collaborators, run on the in-memory fakes (spec 20)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from bundlemcp.application.contracts.live_state.rate_result import RateResult
from bundlemcp.application.errors import InvalidInputError, OAuthError
from bundlemcp.application.oauth_server import (
    AuthorizationCodeIssuer,
    ClientRegistrationService,
    ClientResolver,
    ConsentService,
    MetadataDocumentClientSource,
    PendingAuthorization,
    RegisteredClientSource,
)
from bundlemcp.application.schemas import ClientRegistrationRequest
from bundlemcp.domain.oauth.client_id_metadata_document import ClientIdMetadataDocument
from bundlemcp.domain.oauth.oauth_client import OAuthClient
from bundlemcp.domain.oauth.oauth_error_code import OAuthErrorCode
from bundlemcp.domain.oauth.redirect_uri_allow_list import RedirectUriAllowList
from bundlemcp.domain.oauth.registration_policy import RegistrationPolicy
from bundlemcp.domain.oauth.token_policy import TokenPolicy
from bundlemcp.domain.shared.secrets import hash_token
from bundlemcp.domain.shared.sha256_secret_hasher import Sha256SecretHasher
from bundlemcp.infrastructure.memory.in_memory_unit_of_work import InMemoryUnitOfWork
from bundlemcp.infrastructure.memory.manual_clock import ManualClock
from bundlemcp.infrastructure.memory.sequential_secret_generator import (
    SequentialSecretGenerator,
)

CIMD_URL = "https://client.example/oauth/client.json"
OPEN = RedirectUriAllowList()


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


def _resolver(
    uow: InMemoryUnitOfWork,
    fetcher: FakeFetcher,
    allowed: RedirectUriAllowList = OPEN,
) -> ClientResolver:
    return ClientResolver(
        (
            RegisteredClientSource(uow.oauth_clients),
            MetadataDocumentClientSource(
                uow.oauth_clients, fetcher, allowed_redirect_uris=allowed
            ),
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


async def test_a_document_with_an_unlisted_redirect_uri_is_refused(uow):
    """OAS-13: a configured allow-list applies to the redirect URIs a document declares."""
    fetcher = FakeFetcher(
        ClientIdMetadataDocument(client_id=CIMD_URL, redirect_uris=["https://client.example/cb"])
    )
    with pytest.raises(InvalidInputError, match="invalid_redirect_uri"):
        await _resolver(
            uow, fetcher, RedirectUriAllowList.of(["https://claude.ai/cb"])
        ).resolve(CIMD_URL)
    assert await uow.oauth_clients.get(CIMD_URL) is None
    listed = RedirectUriAllowList.of(["https://client.example/cb"])
    assert await _resolver(uow, fetcher, listed).resolve(CIMD_URL) is not None


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


class CountingRateLimiter:
    """Allows a fixed number of events and remembers which scopes it was asked about."""

    def __init__(self, limit_reached: bool = False) -> None:
        self.scopes: list[str] = []
        self._limit_reached = limit_reached

    async def check(
        self, scope: str, limit: int, window: int, *, fail_closed: bool = False
    ) -> RateResult:
        self.scopes.append(scope)
        return RateResult(allowed=not self._limit_reached)

    async def peek(
        self, scope: str, limit: int, window: int, *, fail_closed: bool = False
    ) -> RateResult:
        return RateResult(allowed=not self._limit_reached)


def _registrations(
    uow: InMemoryUnitOfWork, limiter: CountingRateLimiter, *, allowed: list[str], quota: int = 100
) -> ClientRegistrationService:
    return ClientRegistrationService(
        uow,
        public_base="http://gw",
        generator=SequentialSecretGenerator(),
        hasher=Sha256SecretHasher(),
        policy=RegistrationPolicy(
            allowed_redirect_uris=RedirectUriAllowList.of(allowed),
            per_ip_limit=10,
            per_ip_window=3600,
            max_unused_clients=quota,
        ),
        rate_limiter=limiter,
    )


async def test_allow_listed_registration_never_touches_the_per_ip_counter(uow):
    """OAS-12: a registration whose redirect URIs are all listed is exempt from the IP budget."""
    limiter = CountingRateLimiter(limit_reached=True)
    service = _registrations(uow, limiter, allowed=["https://claude.ai/cb"])
    request = ClientRegistrationRequest(redirect_uris=["https://claude.ai/cb"])
    assert (await service.register(request, "203.0.113.7")).client_id
    assert limiter.scopes == []


async def test_unlisted_registration_counts_against_its_ip(uow):
    """OAS-12: without an allow-list every registration is counted per client IP."""
    limiter = CountingRateLimiter(limit_reached=True)
    service = _registrations(uow, limiter, allowed=[])
    request = ClientRegistrationRequest(redirect_uris=["https://client.example/cb"])
    with pytest.raises(OAuthError) as refused:
        await service.register(request, "203.0.113.7")
    assert refused.value.code == OAuthErrorCode.TOO_MANY_REQUESTS
    assert limiter.scopes == ["dcr:203.0.113.7"]
    assert uow.oauth_clients.rows == []


async def test_refused_redirect_uri_is_answered_before_any_counter_or_query(uow):
    """OAS-2: an unlisted redirect URI is refused in memory, before the IP budget is spent."""
    limiter = CountingRateLimiter()
    service = _registrations(uow, limiter, allowed=["https://claude.ai/cb"])
    request = ClientRegistrationRequest(redirect_uris=["https://evil.example/cb"])
    with pytest.raises(OAuthError) as refused:
        await service.register(request, "203.0.113.7")
    assert refused.value.code == OAuthErrorCode.INVALID_REDIRECT_URI
    assert limiter.scopes == []


async def test_unused_client_quota_applies_to_allow_listed_registrations(uow):
    """SEC-8: the global cap on never-used clients holds even for exempt registrations."""
    service = _registrations(uow, CountingRateLimiter(), allowed=["https://claude.ai/cb"], quota=1)
    request = ClientRegistrationRequest(redirect_uris=["https://claude.ai/cb"])
    await service.register(request, "203.0.113.7")
    with pytest.raises(OAuthError) as refused:
        await service.register(request, "203.0.113.8")
    assert refused.value.code == OAuthErrorCode.TOO_MANY_REQUESTS
