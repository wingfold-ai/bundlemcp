"""Lightweight in-process counters.

Metrics are replica-local by nature (a scraper reads each process on its
own), so plain in-memory counters are correct here. Nothing exports them yet:
there is no /metrics endpoint, so they are only the collection point a future
exporter would read.
"""

from collections import defaultdict


class InProcessCounters:
    def __init__(self) -> None:
        self._counts: dict[str, int] = defaultdict(int)

    def inc(self, name: str, amount: int = 1) -> None:
        self._counts[name] += amount

    def get(self, name: str) -> int:
        return self._counts[name]

    def snapshot(self) -> dict[str, int]:
        return dict(self._counts)


# Canonical metric names, kept stable for the exporter that will read them.
