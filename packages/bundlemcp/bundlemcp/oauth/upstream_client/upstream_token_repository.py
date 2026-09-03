"""Encrypted token sets and client registrations for upstream servers."""

import uuid
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bundlemcp.crypto import TokenCipher
from bundlemcp.models import UpstreamOAuthClient, UpstreamOAuthToken, utcnow
from bundlemcp.oauth.upstream_client.needs_connect import NeedsConnect
from bundlemcp.oauth.upstream_client.upstream_client_config import UpstreamClientConfig
from bundlemcp.oauth.upstream_client.upstream_tokens import UpstreamTokens
from bundlemcp.store import Repository


class UpstreamTokenRepository:
    """Rows keyed (server_id, user_id); a NULL user is the shared connection."""

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], cipher: TokenCipher
    ) -> None:
        self._sessions = session_factory
        self._cipher = cipher

    @staticmethod
    def _criteria(server_id: uuid.UUID, user_id: uuid.UUID | None) -> list[object]:
        user_clause = (
            UpstreamOAuthToken.user_id.is_(None)  # type: ignore[union-attr]
            if user_id is None
            else UpstreamOAuthToken.user_id == user_id
        )
        return [UpstreamOAuthToken.server_id == server_id, user_clause]

    async def load(
        self, server_id: uuid.UUID, user_id: uuid.UUID | None
    ) -> UpstreamOAuthToken | None:
        async with self._sessions() as db:
            return await Repository(db, UpstreamOAuthToken).one(*self._criteria(server_id, user_id))

    def decode(self, row: UpstreamOAuthToken) -> UpstreamTokens:
        return UpstreamTokens.model_validate_json(self._cipher.decrypt(row.tokens_encrypted))

    async def save(
        self, server_id: uuid.UUID, user_id: uuid.UUID | None, tokens: UpstreamTokens
    ) -> None:
        blob = self._cipher.encrypt(tokens.model_dump_json())
        expires_at = utcnow() + timedelta(seconds=tokens.expires_in) if tokens.expires_in else None
        async with self._sessions() as db:
            rows = Repository(db, UpstreamOAuthToken)
            row = await rows.one(*self._criteria(server_id, user_id))
            if row is None:
                row = UpstreamOAuthToken(
                    server_id=server_id, user_id=user_id, tokens_encrypted=blob
                )
            row.tokens_encrypted = blob
            row.expires_at = expires_at
            row.is_valid = True
            if tokens.account_hint:
                row.account_hint = tokens.account_hint
            rows.add(row)
            await db.commit()

    async def invalidate(self, server_id: uuid.UUID, user_id: uuid.UUID | None) -> None:
        """Mark the connection broken so callers are asked to reconnect."""
        async with self._sessions() as db:
            rows = Repository(db, UpstreamOAuthToken)
            row = await rows.one(*self._criteria(server_id, user_id))
            if row is not None:
                row.is_valid = False
                rows.add(row)
                await db.commit()

    async def delete(self, server_id: uuid.UUID, user_id: uuid.UUID | None) -> None:
        async with self._sessions() as db:
            rows = Repository(db, UpstreamOAuthToken)
            row = await rows.one(*self._criteria(server_id, user_id))
            if row is not None:
                await rows.delete(row)
                await db.commit()

    async def client_config(self, server_id: uuid.UUID) -> UpstreamClientConfig:
        async with self._sessions() as db:
            client = await Repository(db, UpstreamOAuthClient).one(
                UpstreamOAuthClient.server_id == server_id
            )
        if client is None or not client.client_id:
            raise NeedsConnect("server", "no_client_config")
        secret = (
            self._cipher.decrypt(client.client_secret_encrypted)
            if client.client_secret_encrypted
            else None
        )
        return UpstreamClientConfig(
            client_id=client.client_id, client_secret=secret, metadata=client.metadata_ or {}
        )
