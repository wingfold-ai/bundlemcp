from dataclasses import dataclass


@dataclass(frozen=True)
class MeterDecision:
    allowed: bool
    reason: str | None = None  # e.g. "insufficient_credits"
