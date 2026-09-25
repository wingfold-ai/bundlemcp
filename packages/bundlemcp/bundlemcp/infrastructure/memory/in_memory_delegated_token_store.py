from bundlemcp.domain.delegation.delegated_token import DelegatedToken


class InMemoryDelegatedTokenStore:
    """Delegated tokens in a dict; expiry is left to the record's own timestamp."""

    def __init__(self) -> None:
        self.records: dict[str, DelegatedToken] = {}

    async def put(self, token_hash: str, token: DelegatedToken, *, ttl_seconds: int) -> None:
        self.records[token_hash] = token

    async def get(self, token_hash: str) -> DelegatedToken | None:
        return self.records.get(token_hash)
