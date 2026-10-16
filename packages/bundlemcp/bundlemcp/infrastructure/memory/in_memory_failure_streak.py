import uuid


class InMemoryFailureStreak:
    """Failure streaks in a dict; share one instance to stand in for several replicas."""

    def __init__(self) -> None:
        self.streaks: dict[uuid.UUID, int] = {}

    async def record_failure(self, server_id: uuid.UUID) -> int:
        self.streaks[server_id] = self.streaks.get(server_id, 0) + 1
        return self.streaks[server_id]

    async def reset(self, server_id: uuid.UUID) -> None:
        self.streaks.pop(server_id, None)
