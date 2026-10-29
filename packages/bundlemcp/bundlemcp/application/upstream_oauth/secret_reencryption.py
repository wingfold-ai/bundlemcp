"""Moving every stored secret under the primary key after a key rotation."""

import uuid
from collections.abc import Callable
from typing import Any

import structlog

from bundlemcp.application.contracts.persistence.stored_secrets import StoredSecrets
from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWork, UnitOfWorkFactory
from bundlemcp.application.contracts.secret_cipher import DecryptionError, SecretCipher
from bundlemcp.application.upstream_oauth.reencryption_sweep import ReencryptionSweep

log = structlog.get_logger(__name__)

BATCH_SIZE = 100


class SecretReencryption:
    """Re-encrypts upstream tokens, client secrets and static headers still under an older key.

    First seals the static headers of servers still storing them in plaintext,
    then pages through each table, one short unit of work per batch. Every
    write is a compare-and-set, so a value a request rewrote meanwhile is left
    as that request wrote it, which is already under the primary key.
    """

    def __init__(self, units: UnitOfWorkFactory, cipher: SecretCipher) -> None:
        self._units = units
        self._cipher = cipher

    async def sweep(self) -> ReencryptionSweep:
        result = ReencryptionSweep()
        await self._seal(result)
        await self._sweep(result, lambda uow: uow.upstream_tokens, lambda t: t.tokens_encrypted)
        await self._sweep(
            result, lambda uow: uow.upstream_clients, lambda c: c.client_secret_encrypted
        )
        await self._sweep(
            result, lambda uow: uow.servers.header_ciphertexts(), lambda h: h.ciphertext
        )
        return result

    async def _seal(self, result: ReencryptionSweep) -> None:
        """Encrypt plaintext static headers in batches, until a batch finds fewer to seal."""
        while True:
            async with self._units.open() as uow:
                sealed = await uow.servers.seal_plaintext_headers(BATCH_SIZE)
                await uow.commit()
            result.sealed += sealed
            if sealed < BATCH_SIZE:
                return

    async def _sweep(
        self,
        result: ReencryptionSweep,
        table: Callable[[UnitOfWork], StoredSecrets],
        stored: Callable[[Any], str | None],
    ) -> None:
        after: uuid.UUID | None = None
        while True:
            async with self._units.open() as uow:
                secrets = table(uow)
                rows = await secrets.page_after(after, BATCH_SIZE)
                for row in rows:
                    await self._move(result, secrets, row.id, stored(row))
                await uow.commit()
            if len(rows) < BATCH_SIZE:
                return
            after = rows[-1].id

    async def _move(
        self,
        result: ReencryptionSweep,
        secrets: StoredSecrets,
        row_id: uuid.UUID,
        value: str | None,
    ) -> None:
        if not value or self._cipher.is_current(value):
            return
        try:
            rewritten = self._cipher.reencrypt(value)
        except DecryptionError:
            result.undecryptable += 1
            return
        try:
            replaced = await secrets.replace_ciphertext(row_id, value, rewritten)
        except Exception:
            log.warning("token_encryption.reencrypt_failed", row_id=str(row_id))
            result.remaining_on_old_key += 1
            return
        if replaced:
            result.rewritten += 1
        # otherwise a request rewrote the value meanwhile, under the primary key
