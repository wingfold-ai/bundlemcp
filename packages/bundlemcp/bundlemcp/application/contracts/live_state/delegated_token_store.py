from typing import Protocol, runtime_checkable

from bundlemcp.domain.delegation.delegated_token import DelegatedToken


@runtime_checkable
class DelegatedTokenStore(Protocol):
    """Where delegated tokens live between issue and expiry, keyed by their hash only."""

    async def put(self, token_hash: str, token: DelegatedToken, *, ttl_seconds: int) -> None:
        """Keep the record until it expires; the token value itself is never stored."""
        ...

    async def get(self, token_hash: str) -> DelegatedToken | None:
        """The record for a token hash; None when unknown, expired or malformed."""
        ...
