class InMemoryStreamPresence:
    """Held streams in a set; holds never expire."""

    def __init__(self) -> None:
        self.held: set[str] = set()

    async def hold(self, stream_id: str) -> None:
        self.held.add(stream_id)

    async def release(self, stream_id: str) -> None:
        self.held.discard(stream_id)

    async def is_held(self, stream_id: str) -> bool:
        return stream_id in self.held
