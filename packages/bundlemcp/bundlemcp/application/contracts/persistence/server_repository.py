import uuid
from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from bundlemcp.application.contracts.persistence.repository import NamedRepository
from bundlemcp.application.contracts.persistence.stored_secrets import StoredSecrets
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.servers.server_observations import ServerObservations


@runtime_checkable
class ServerRepository(NamedRepository[McpServer], Protocol):
    """Registered upstream servers.

    Static header values are handed out in plaintext; whether they are stored
    encrypted is the storage's business, governed by the encryption keys.
    """

    async def by_ids(self, ids: Iterable[uuid.UUID]) -> list[McpServer]:
        """The servers with these ids, in name order; unknown ids are skipped."""
        ...

    async def record_observations(
        self, server_id: uuid.UUID, observations: ServerObservations
    ) -> bool:
        """Write what contacting the server found out onto the server as it is stored now.

        Leaves its name and configuration as they are stored, and never creates a server:
        returns False, writing nothing, when the server no longer exists.
        """
        ...

    def header_ciphertexts(self) -> StoredSecrets:
        """The servers' encrypted static headers, for moving them under the primary key.

        Each item the view pages carries ``id`` and ``ciphertext``; replacing a value is a
        compare-and-set on the stored ciphertext.
        """
        ...

    async def seal_plaintext_headers(self, limit: int) -> int:
        """Encrypt the static headers of up to ``limit`` servers still storing plaintext.

        A server written meanwhile is left as it was written. Returns how many were sealed;
        always 0 when no encryption key is configured.
        """
        ...

    async def count_plaintext_headers(self) -> int:
        """How many servers hold static header values in plaintext."""
        ...
