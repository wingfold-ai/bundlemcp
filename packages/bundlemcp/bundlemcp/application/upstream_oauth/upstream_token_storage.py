"""Encrypted token sets and client registrations for upstream servers, read and written per call."""

import uuid
from datetime import timedelta

from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWorkFactory
from bundlemcp.application.contracts.secret_cipher import SecretCipher
from bundlemcp.domain.shared.clock import utcnow
from bundlemcp.domain.upstream_oauth.needs_connect import NeedsConnect
from bundlemcp.domain.upstream_oauth.upstream_client_config import UpstreamClientConfig
from bundlemcp.domain.upstream_oauth.upstream_client_registration import (
    UpstreamClientRegistration,
)
from bundlemcp.domain.upstream_oauth.upstream_metadata import UpstreamMetadata
from bundlemcp.domain.upstream_oauth.upstream_oauth_client import UpstreamOAuthClient
from bundlemcp.domain.upstream_oauth.upstream_oauth_token import UpstreamOAuthToken
from bundlemcp.domain.upstream_oauth.upstream_tokens import UpstreamTokens


class UpstreamTokenStorage:
    """Rows keyed (server_id, user_id); a NULL user is the shared connection.

    Runs outside any request transaction, because a token is refreshed in the
    middle of a tool call, so every operation opens and commits its own unit
    of work.
    """

    def __init__(self, units: UnitOfWorkFactory, cipher: SecretCipher) -> None:
        self._units = units
        self._cipher = cipher

    async def load(
        self, server_id: uuid.UUID, user_id: uuid.UUID | None
    ) -> UpstreamOAuthToken | None:
        async with self._units.open() as uow:
            return await uow.upstream_tokens.find(server_id, user_id)

    def decode(self, row: UpstreamOAuthToken) -> UpstreamTokens:
        return UpstreamTokens.model_validate_json(self._cipher.decrypt(row.tokens_encrypted))

    async def save(
        self, server_id: uuid.UUID, user_id: uuid.UUID | None, tokens: UpstreamTokens
    ) -> None:
        blob = self._cipher.encrypt(tokens.model_dump_json())
        expires_at = utcnow() + timedelta(seconds=tokens.expires_in) if tokens.expires_in else None
        async with self._units.open() as uow:
            row = await uow.upstream_tokens.find(server_id, user_id)
            if row is None:
                row = UpstreamOAuthToken(
                    server_id=server_id, user_id=user_id, tokens_encrypted=blob
                )
            row.tokens_encrypted = blob
            row.expires_at = expires_at
            row.is_valid = True
            if tokens.account_hint:
                row.account_hint = tokens.account_hint
            uow.upstream_tokens.add(row)
            await uow.commit()

    async def invalidate(self, server_id: uuid.UUID, user_id: uuid.UUID | None) -> None:
        """Mark the connection broken so callers are asked to reconnect."""
        async with self._units.open() as uow:
            row = await uow.upstream_tokens.find(server_id, user_id)
            if row is not None:
                row.is_valid = False
                uow.upstream_tokens.add(row)
                await uow.commit()

    async def delete(self, server_id: uuid.UUID, user_id: uuid.UUID | None) -> None:
        async with self._units.open() as uow:
            row = await uow.upstream_tokens.find(server_id, user_id)
            if row is not None:
                await uow.upstream_tokens.delete(row)
                await uow.commit()

    async def any_valid_user_connection(self, server_id: uuid.UUID) -> UpstreamOAuthToken | None:
        """Some user's working connection to a per-user server, for discovery to borrow."""
        async with self._units.open() as uow:
            return await uow.upstream_tokens.any_valid_user_connection(server_id)

    async def find_client_config(self, server_id: uuid.UUID) -> UpstreamClientConfig | None:
        """The client this gateway uses at the server's authorization server, if it has one."""
        async with self._units.open() as uow:
            client = await uow.upstream_clients.for_server(server_id)
        if client is None or not client.client_id:
            return None
        secret = (
            self._cipher.decrypt(client.client_secret_encrypted)
            if client.client_secret_encrypted
            else None
        )
        return UpstreamClientConfig(
            client_id=client.client_id, client_secret=secret, metadata=client.metadata_ or {}
        )

    async def client_config(self, server_id: uuid.UUID) -> UpstreamClientConfig:
        config = await self.find_client_config(server_id)
        if config is None:
            raise NeedsConnect("server", "no_client_config")
        return config

    async def save_registration(
        self,
        server_id: uuid.UUID,
        registration: UpstreamClientRegistration,
        meta: UpstreamMetadata,
    ) -> None:
        """Keep a dynamically registered client, with the metadata it was registered against.

        A client id an admin stored in the meantime is never overwritten.
        """
        async with self._units.open() as uow:
            client = await uow.upstream_clients.for_server(server_id)
            if client is not None and client.client_id:
                return
            if client is None:
                client = UpstreamOAuthClient(server_id=server_id)
            client.client_id = registration.client_id
            client.client_secret_encrypted = (
                self._cipher.encrypt(registration.client_secret)
                if registration.client_secret
                else None
            )
            client.metadata_ = meta.model_dump(exclude_none=True)
            uow.upstream_clients.add(client)
            await uow.commit()
