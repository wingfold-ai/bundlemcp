import json
import uuid
from collections.abc import Awaitable, Callable, Iterable

import structlog
from sqlalchemy import ColumnElement, Text, and_, cast, not_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bundlemcp.application.contracts.persistence.page_slice import PageSlice
from bundlemcp.application.contracts.persistence.stored_ciphertext import StoredCiphertext
from bundlemcp.application.contracts.secret_cipher import DecryptionError, SecretCipher
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.servers.protocol_mode import NegotiationMode
from bundlemcp.domain.servers.server_observations import ServerObservations
from bundlemcp.infrastructure.postgres.rows.mcp_server_row import McpServerRow
from bundlemcp.infrastructure.postgres.sqlalchemy_repository import SqlAlchemyRepository

log = structlog.get_logger(__name__)

# The column keeps the handshake-only mode's pre-rename spelling until every replica reads
# the new one; the release before the rename hands the stored value straight to the client.
STORED_SESSION_MODE = "legacy"


class SqlAlchemyServerRepository(SqlAlchemyRepository[McpServer, McpServerRow]):
    """Servers, with their static header values encrypted at rest when a cipher is held.

    With a cipher, a server's headers are written as one ciphertext of their JSON
    object and the plaintext column is left empty; a row that still holds
    plaintext is read from it. Without a cipher, the plaintext column is read and
    written as is. A ciphertext that cannot be decrypted reads as no headers, and
    is written back unchanged when the same server is saved with no headers in
    this unit of work, so an unrelated edit never destroys a value a restored key
    could still decrypt.
    """

    def __init__(self, session: AsyncSession, cipher: SecretCipher | None = None) -> None:
        super().__init__(session, McpServer, McpServerRow)
        self._cipher = cipher
        # ciphertexts read in this unit of work that no held key decrypts, by server id
        self._undecryptable: dict[uuid.UUID, str] = {}

    # ---- mapping --------------------------------------------------------------------------

    def _to_entity(self, row: McpServerRow) -> McpServer:
        if row.protocol_mode == STORED_SESSION_MODE:
            # validated from a copy: assigning to the row would write the new spelling back
            server = McpServer.model_validate(
                {**row.model_dump(), "protocol_mode": NegotiationMode.SESSION}
            )
        else:
            server = super()._to_entity(row)
        if row.static_headers_encrypted is not None:
            server.static_headers = self._decrypt_headers(row.id, row.static_headers_encrypted)
        return server

    def _to_row(self, entity: McpServer) -> McpServerRow:
        row = super()._to_row(entity)
        row.protocol_mode = (
            STORED_SESSION_MODE
            if entity.protocol_mode == NegotiationMode.SESSION
            else str(entity.protocol_mode)
        )
        kept = self._undecryptable.get(entity.id)
        if kept is not None and not entity.static_headers:
            row.static_headers = {}
            row.static_headers_encrypted = kept
        elif self._cipher is not None and entity.static_headers:
            row.static_headers = {}
            row.static_headers_encrypted = self._cipher.encrypt(_canonical(entity.static_headers))
        return row

    def _decrypt_headers(self, server_id: uuid.UUID, ciphertext: str) -> dict[str, str]:
        if self._cipher is not None:
            try:
                return json.loads(self._cipher.decrypt(ciphertext))
            except DecryptionError:
                pass
        log.warning("server.static_headers_undecryptable", server_id=str(server_id))
        self._undecryptable[server_id] = ciphertext
        return {}

    # ---- queries --------------------------------------------------------------------------

    async def page(self, *, offset: int, limit: int) -> PageSlice[McpServer]:
        return await super().page(
            offset=offset, limit=limit, order_by=(McpServerRow.created_at, McpServerRow.id)
        )

    async def by_ids(self, ids: Iterable[uuid.UUID]) -> list[McpServer]:
        wanted = list(ids)
        if not wanted:
            return []
        return await self.all(McpServerRow.id.in_(wanted), order_by=(McpServerRow.name,))  # type: ignore[attr-defined]

    async def record_observations(
        self, server_id: uuid.UUID, observations: ServerObservations
    ) -> bool:
        # an update, never a merge: a merge of a row deleted meanwhile inserts it again
        changed = await self.update_where(McpServerRow.id == server_id, **observations.model_dump())
        return changed == 1

    # ---- encryption at rest ---------------------------------------------------------------

    def header_ciphertexts(self) -> ServerHeaderCiphertexts:
        return ServerHeaderCiphertexts(self._session, self.flush_pending)

    async def seal_plaintext_headers(self, limit: int) -> int:
        cipher = self._cipher  # narrowed once, for every row the loop below seals
        if cipher is None:
            return 0
        await self.flush_pending()
        statement = (
            select(McpServerRow.id, _headers_text())
            .where(_holds_plaintext_headers())
            .order_by(McpServerRow.id)
            .limit(limit)
        )
        candidates = (await self._session.execute(statement)).all()
        sealed = 0
        for server_id, stored in candidates:
            sealed += await self._seal(cipher, server_id, stored)
        return sealed

    async def _seal(self, cipher: SecretCipher, server_id: uuid.UUID, stored: str) -> int:
        """Encrypt one row's plaintext headers, unless it was written since ``stored`` was read."""
        ciphertext = cipher.encrypt(_canonical(json.loads(stored)))
        return await self.update_where(
            McpServerRow.id == server_id,
            McpServerRow.static_headers_encrypted.is_(None),  # type: ignore[union-attr]
            _headers_text() == stored,
            static_headers={},
            static_headers_encrypted=ciphertext,
        )

    async def count_plaintext_headers(self) -> int:
        return await self.count(_holds_plaintext_headers())


class ServerHeaderCiphertexts:
    """The servers' encrypted static headers, as a table the re-encryption sweep pages."""

    def __init__(self, session: AsyncSession, flush: Callable[[], Awaitable[None]]) -> None:
        self._session = session
        self._flush = flush  # the repository's staged writes land before any read

    async def page_after(self, after: uuid.UUID | None, limit: int) -> list[StoredCiphertext]:
        encrypted = McpServerRow.static_headers_encrypted
        statement = (
            select(McpServerRow.id, encrypted)
            .where(encrypted.is_not(None))  # type: ignore[union-attr]
            .order_by(McpServerRow.id)
            .limit(limit)
        )
        if after is not None:
            statement = statement.where(McpServerRow.id > after)
        await self._flush()
        rows = (await self._session.execute(statement)).all()
        return [StoredCiphertext(id=row_id, ciphertext=value) for row_id, value in rows]

    async def replace_ciphertext(self, id: uuid.UUID, expected: str, new: str) -> bool:
        await self._flush()
        statement = (
            update(McpServerRow)
            .where(
                McpServerRow.id == id,  # type: ignore[arg-type]
                McpServerRow.static_headers_encrypted == expected,  # type: ignore[arg-type]
            )
            .values(static_headers_encrypted=new)
            .execution_options(synchronize_session="fetch")
        )
        return (await self._session.execute(statement)).rowcount == 1


def _canonical(headers: dict[str, str]) -> str:
    """One JSON text per header set, so equal headers always encrypt the same plaintext."""
    return json.dumps(headers, sort_keys=True, separators=(",", ":"))


def _headers_text() -> ColumnElement[str]:
    """The plaintext header column as stored text; ``json`` has no equality in Postgres."""
    return cast(McpServerRow.static_headers, Text)


def _holds_plaintext_headers() -> ColumnElement[bool]:
    """Rows whose plaintext column carries at least one header value."""
    stored = _headers_text()
    return and_(
        McpServerRow.static_headers.is_not(None),  # type: ignore[attr-defined]
        not_(or_(stored == "{}", stored == "null")),
    )
