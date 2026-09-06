"""Fetching a client's metadata document over HTTPS, cached for its declared lifetime."""

import hashlib
import re

import httpx
from pydantic import ValidationError
from redis.asyncio import Redis

from bundlemcp.gateway.egress import EgressDenied, check_url_allowed
from bundlemcp.services.errors import InvalidInputError
from bundlemcp.services.oauth_server import ClientIdMetadataDocument
from bundlemcp.settings import Settings

CLIENT_METADATA_KEY = "bmcp:cimd:{digest}"  # OAS-13 cached client metadata documents
HTTP_TIMEOUT = 10
DEFAULT_TTL = 3600  # OAS-13: bounded lifetime when the document names none
MAX_TTL = 3600
MIN_TTL = 60
_MAX_AGE = re.compile(r"max-age=(\d+)")


class HttpxClientMetadataFetcher:
    """The real fetch: HTTPS only, through the egress policy, one hop, no redirects."""

    def __init__(self, settings: Settings, redis: Redis) -> None:
        self._settings = settings
        self._redis = redis

    async def fetch(self, client_id_url: str) -> ClientIdMetadataDocument:
        key = CLIENT_METADATA_KEY.format(digest=hashlib.sha256(client_id_url.encode()).hexdigest())
        cached = await self._redis.get(key)
        if cached is not None:
            try:
                return ClientIdMetadataDocument.model_validate_json(cached)
            except ValidationError:
                pass  # a stale shape is refetched below
        try:
            check_url_allowed(client_id_url, self._settings)  # SEC-1
        except EgressDenied as exc:
            raise InvalidInputError("client metadata document URL is not allowed") from exc
        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, follow_redirects=False) as client:
                response = await client.get(client_id_url, headers={"Accept": "application/json"})
            response.raise_for_status()
            document = ClientIdMetadataDocument.model_validate(response.json())
        except (httpx.HTTPError, ValueError, ValidationError) as exc:
            raise InvalidInputError("client metadata document could not be fetched") from exc
        await self._redis.set(key, document.model_dump_json(), ex=self._ttl(response))
        return document

    @staticmethod
    def _ttl(response: httpx.Response) -> int:
        match = _MAX_AGE.search(response.headers.get("cache-control", ""))
        ttl = int(match.group(1)) if match else DEFAULT_TTL
        return max(MIN_TTL, min(MAX_TTL, ttl))
