"""Forgetting what a server's credentials were obtained for, once its URL moves."""

import uuid

from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWork
from bundlemcp.domain.access.principal import Principal
from bundlemcp.domain.audit.audit_record import AuditRecord
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.servers.url_change import UrlChange

CREDENTIALS_REVOKED = "upstream.credentials_revoked"


class UpstreamCredentialRevocation:
    """Stages the removal of credentials that belong to a server's previous URL.

    Nothing is committed here: the changes ride on the transaction of the write
    that moved the URL, so they land together with it or not at all.
    """

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def revoke(self, server: McpServer, move: UrlChange, *, actor: Principal | None) -> None:
        """Remove what ``move`` leaves behind, and record it when anything was removed.

        Every stored token goes, shared and per user. A client the gateway obtained
        itself goes too, so the next connect registers at the new resource's
        authorization server. A client an admin stored keeps its id and grant but
        forgets the old server, and loses its secret when the origin moves.
        """
        if not move.moves_resource:
            return
        tokens = await self._uow.upstream_tokens.for_server(server.id)
        for token in tokens:
            await self._uow.upstream_tokens.delete(token)
        client_changed = False
        client = await self._uow.upstream_clients.for_server(server.id)
        if client is not None and not client.metadata_.is_admin_stored:
            await self._uow.upstream_clients.delete(client)
            client_changed = True
        elif client is not None:
            forgotten = client.metadata_.forgetting_server()
            drops_secret = move.moves_origin and client.client_secret_encrypted is not None
            client_changed = drops_secret or forgotten.model_dump() != client.metadata_.model_dump()
            client.metadata_ = forgotten
            if drops_secret:
                client.client_secret_encrypted = None
            self._uow.upstream_clients.add(client)
        if tokens or client_changed:
            self._uow.audit_records.add(
                AuditRecord.management_event(
                    CREDENTIALS_REVOKED,
                    user_id=uuid.UUID(actor.user_id) if actor and actor.user_id else None,
                    api_key_id=uuid.UUID(actor.api_key_id) if actor and actor.api_key_id else None,
                    auth_method=None,
                )
            )
