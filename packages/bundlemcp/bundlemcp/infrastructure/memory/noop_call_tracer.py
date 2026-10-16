from collections.abc import Iterator
from contextlib import contextmanager


class NoopSpan:
    """A span that keeps nothing."""

    def set_attribute(self, key: str, value: str) -> None:
        return None


NOOP_SPAN = NoopSpan()


class NoopCallTracer:
    """Tracing off: each span is a context manager that does nothing."""

    @contextmanager
    def span(self, name: str, attributes: dict[str, str]) -> Iterator[NoopSpan]:
        yield NOOP_SPAN
