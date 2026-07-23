from dataclasses import dataclass


@dataclass(frozen=True)
class MeterContext:
    sub: str | None  # user id, or "api_key:<id>", or None for anonymous
    email: str | None
    endpoint: str
    bundle: str
    server: str
    tool: str
    idempotency_key: str  # once per client invocation; internal retries reuse it
