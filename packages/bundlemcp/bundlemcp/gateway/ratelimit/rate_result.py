from dataclasses import dataclass


@dataclass
class RateResult:
    allowed: bool
    retry_after: int = 0  # seconds until the window rolls over
    remaining: int = 0
