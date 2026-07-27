"""Lightweight in-process counters.

Metrics are replica-local by nature (each Prometheus target scrapes its own
process), so plain in-memory counters are correct here. The /metrics endpoint
exports these; this module is the collection point it reads.
"""

from collections import defaultdict


class Counters:
    def __init__(self) -> None:
        self._counts: dict[str, int] = defaultdict(int)

    def inc(self, name: str, amount: int = 1) -> None:
        self._counts[name] += amount

    def get(self, name: str) -> int:
        return self._counts[name]

    def snapshot(self) -> dict[str, int]:
        return dict(self._counts)
