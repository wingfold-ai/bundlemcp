"""Fetching a client's metadata document over HTTPS, cached for its declared lifetime.

Anyone can trigger this fetch before signing in, by naming a URL as their
client id, so it is narrower than other egress: public addresses only, a
small body, one deadline for the whole fetch, and a failure remembered for a
minute so the same URL cannot be used to make the gateway fetch in a loop.
"""

import asyncio
import hashlib
import json
import re
from collections.abc import Callable
from functools import partial
from urllib.parse import urlparse

import httpx
import structlog
from pydantic import ValidationError
from redis.asyncio import Redis

from bundlemcp.application.oauth_server import ClientIdMetadataDocument
from bundlemcp.application.settings.settings import Settings
from bundlemcp.infrastructure.egress.egress_policy import EgressDenied, check_url_allowed
from bundlemcp.infrastructure.egress.egress_scope import EgressScope
from bundlemcp.infrastructure.httpx.cached_fetch_failure import (
    CachedFetchFailure,
    FetchFailureKind,
)
from bundlemcp.infrastructure.httpx.guarded_client import guarded_client

log = structlog.get_logger(__name__)

CLIENT_METADATA_KEY = "bmcp:cimd:{digest}"  # cached client metadata documents
FAILED_FETCH_KEY = "bmcp:cimd:fail:{digest}"  # recently failed fetches
FETCH_DEADLINE = 5  # seconds, from connect to the last byte
MAX_DOCUMENT_BYTES = 16 * 1024  # real documents are under 2 KiB
FAILURE_TTL = 60
DEFAULT_TTL = 3600  # bounded lifetime when the document names none
MAX_TTL = 3600
MIN_TTL = 60
_MAX_AGE = re.compile(r"max-age=(\d+)")

ClientFactory = Callable[[], httpx.AsyncClient]


class _FetchFailed(Exception):
    def __init__(self, kind: FetchFailureKind, reason: str) -> None:
        self.kind = kind
        self.reason = reason
        super().__init__(reason)


class HttpxClientMetadataFetcher:
    """The real fetch: HTTPS only, public addresses only, one hop, no redirects, bounded."""

    def __init__(
        self,
        settings: Settings,
        redis: Redis,
        *,
        client_factory: ClientFactory | None = None,
    ) -> None:
        self._settings = settings
        self._redis = redis
        self._client_factory = client_factory or partial(
            guarded_client,
            settings,
            scope=EgressScope.PUBLIC,
            timeout=FETCH_DEADLINE,
            follow_redirects=False,
        )

    async def fetch(self, client_id_url: str) -> ClientIdMetadataDocument:
        digest = hashlib.sha256(client_id_url.encode()).hexdigest()
        cached = await self._redis.get(CLIENT_METADATA_KEY.format(digest=digest))
        if cached is not None:
            try:
                return ClientIdMetadataDocument.model_validate_json(cached)
            except ValidationError:
                pass  # a stale shape is refetched below
        failed_key = FAILED_FETCH_KEY.format(digest=digest)
        recent = await self._recent_failure(failed_key)
        if recent is not None:
            raise recent.error()
        try:
            document, ttl = await self._fetch(client_id_url)
        except _FetchFailed as exc:
            log.warning(
                "cimd.fetch_failed", host=urlparse(client_id_url).hostname, reason=exc.reason
            )
            failure = CachedFetchFailure(kind=exc.kind)
            await self._redis.set(failed_key, failure.model_dump_json(), ex=FAILURE_TTL)
            raise failure.error() from exc
        await self._redis.set(
            CLIENT_METADATA_KEY.format(digest=digest), document.model_dump_json(), ex=ttl
        )
        return document

    async def _recent_failure(self, failed_key: str) -> CachedFetchFailure | None:
        raw = await self._redis.get(failed_key)
        if raw is None:
            return None
        try:
            return CachedFetchFailure.model_validate_json(raw)
        except ValidationError:
            return None  # a stale shape is fetched again

    async def _fetch(self, client_id_url: str) -> tuple[ClientIdMetadataDocument, int]:
        """The validated document and how long it may be cached."""
        try:
            check_url_allowed(client_id_url, self._settings, EgressScope.PUBLIC)
            async with asyncio.timeout(FETCH_DEADLINE):
                body, cache_control = await self._read(client_id_url)
            data = json.loads(body)
        except (EgressDenied, httpx.HTTPError, TimeoutError, ValueError) as exc:
            raise _FetchFailed(FetchFailureKind.UNREACHABLE, type(exc).__name__) from exc
        try:
            document = ClientIdMetadataDocument.model_validate(data)
        except ValidationError as exc:
            # a document that arrived but does not parse is the client's fault, not the network's
            raise _FetchFailed(FetchFailureKind.INVALID, "validation") from exc
        return document, self._ttl(cache_control)

    async def _read(self, client_id_url: str) -> tuple[bytes, str]:
        """The response body, refused once it outgrows the cap, and its Cache-Control header."""
        async with (
            self._client_factory() as client,
            client.stream("GET", client_id_url, headers={"Accept": "application/json"}) as response,
        ):
            response.raise_for_status()
            if int(response.headers.get("content-length", 0)) > MAX_DOCUMENT_BYTES:
                raise _FetchFailed(FetchFailureKind.UNREACHABLE, "too large")
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body += chunk
                if len(body) > MAX_DOCUMENT_BYTES:
                    raise _FetchFailed(FetchFailureKind.UNREACHABLE, "too large")
            return bytes(body), response.headers.get("cache-control", "")

    @staticmethod
    def _ttl(cache_control: str) -> int:
        match = _MAX_AGE.search(cache_control)
        ttl = int(match.group(1)) if match else DEFAULT_TTL
        return max(MIN_TTL, min(MAX_TTL, ttl))
