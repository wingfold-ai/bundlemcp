from bundlemcp.application.metering.paused_invocation import PausedInvocation


class InMemoryPausedInvocations:
    """Paused invocations in a dict, for tests; claims are atomic within one event loop."""

    def __init__(self) -> None:
        self.records: dict[str, PausedInvocation] = {}

    async def pause(self, invocation: PausedInvocation) -> None:
        self.records[invocation.context.idempotency_key] = invocation

    async def claim(self, idempotency_key: str) -> PausedInvocation | None:
        return self.records.pop(idempotency_key, None)

    async def expired(self, now: float, limit: int) -> list[str]:
        overdue = sorted(
            (record.expires_at, key)
            for key, record in self.records.items()
            if record.expires_at < now
        )
        return [key for _, key in overdue[:limit]]
