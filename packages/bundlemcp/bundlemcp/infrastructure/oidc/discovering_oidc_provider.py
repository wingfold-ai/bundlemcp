"""An identity provider whose discovery document is fetched when it can be, not only at startup."""

import asyncio
import math
import time
from collections.abc import Awaitable, Callable

import structlog

from bundlemcp.domain.access.oidc_claims import OidcClaims
from bundlemcp.domain.access.oidc_error import OidcError
from bundlemcp.domain.access.oidc_unavailable import OidcUnavailable
from bundlemcp.infrastructure.oidc.jose_oidc_provider import JoseOidcProvider

log = structlog.get_logger(__name__)

Discover = Callable[[], Awaitable[JoseOidcProvider]]
Clock = Callable[[], float]

# ADM-7: the floor between two discovery attempts a login may trigger, so a
# burst of logins while the IdP is down does not become a burst of fetches.
LOGIN_RETRY_FLOOR_SECONDS = 5
# The background loop's backoff while discovery keeps failing.
BACKOFF_INITIAL_SECONDS = 1
BACKOFF_CAP_SECONDS = 60
# How often a discovery document that was fetched is fetched again.
REFRESH_INTERVAL_SECONDS = 3600


class DiscoveringOidcProvider:
    """Serves logins from the last discovery document that was fetched successfully.

    A failed fetch is never cached. Until the first fetch succeeds, a login
    retries discovery itself (at most once per retry floor), and a background
    loop retries with capped exponential backoff, so an IdP that comes up after
    the gateway is picked up without a restart. Once fetched, the document is
    refreshed periodically; a failed refresh keeps the document already held.
    The signing keys are fetched on every code exchange, so a key rotation needs
    no refresh here.
    """

    def __init__(self, discover: Discover, *, clock: Clock = time.monotonic) -> None:
        self._discover = discover
        self._clock = clock
        self._current: JoseOidcProvider | None = None
        self._last_attempt: float | None = None
        self._lock = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None

    async def authorize_url(
        self, *, state: str, nonce: str, redirect_uri: str, code_challenge: str
    ) -> str:
        provider = await self._resolve()
        return await provider.authorize_url(
            state=state, nonce=nonce, redirect_uri=redirect_uri, code_challenge=code_challenge
        )

    async def exchange(
        self, *, code: str, redirect_uri: str, nonce: str, code_verifier: str
    ) -> OidcClaims:
        provider = await self._resolve()
        return await provider.exchange(
            code=code, redirect_uri=redirect_uri, nonce=nonce, code_verifier=code_verifier
        )

    async def refresh(self) -> None:
        """Fetch the discovery document now; raise ``OidcUnavailable`` if that fails."""
        async with self._lock:
            await self._attempt()

    def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None

    async def _resolve(self) -> JoseOidcProvider:
        if self._current is not None:
            return self._current
        async with self._lock:
            if self._current is not None:  # another request discovered it meanwhile
                return self._current
            if self._last_attempt is not None:
                wait = self._last_attempt + LOGIN_RETRY_FLOOR_SECONDS - self._clock()
                if wait > 0:
                    raise OidcUnavailable(
                        "identity provider not reachable yet", retry_after=math.ceil(wait)
                    )
            return await self._attempt()

    async def _attempt(self) -> JoseOidcProvider:
        self._last_attempt = self._clock()
        try:
            provider = await self._discover()
        except OidcError as exc:
            # A refresh failure keeps the document already held; logins go on.
            log.warning("oidc.discovery_failed", have_document=self._current is not None)
            raise OidcUnavailable(
                "identity provider not reachable yet", retry_after=LOGIN_RETRY_FLOOR_SECONDS
            ) from exc
        if self._current is None:
            log.info("oidc.discovered")
        self._current = provider
        return provider

    async def _run(self) -> None:
        backoff = BACKOFF_INITIAL_SECONDS
        while True:
            try:
                await self.refresh()
            except OidcUnavailable:
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, BACKOFF_CAP_SECONDS)
                continue
            except Exception:
                log.warning("oidc.discovery_crashed", exc_info=True)
                await asyncio.sleep(BACKOFF_CAP_SECONDS)
                continue
            backoff = BACKOFF_INITIAL_SECONDS
            await asyncio.sleep(REFRESH_INTERVAL_SECONDS)
