import uuid
from typing import Any, Protocol


class StoredSecrets(Protocol):
    """A table of encrypted values the sweep can page through and rewrite in place."""

    async def page_after(self, after: uuid.UUID | None, limit: int) -> list[Any]: ...

    async def replace_ciphertext(self, id: uuid.UUID, expected: str, new: str) -> bool: ...
