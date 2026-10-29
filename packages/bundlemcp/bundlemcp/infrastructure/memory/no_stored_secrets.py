import uuid

from bundlemcp.application.contracts.persistence.stored_ciphertext import StoredCiphertext


class NoStoredSecrets:
    """A table of encrypted values that holds none: the fakes keep their secrets in plaintext."""

    async def page_after(self, after: uuid.UUID | None, limit: int) -> list[StoredCiphertext]:
        return []

    async def replace_ciphertext(self, id: uuid.UUID, expected: str, new: str) -> bool:
        return False
