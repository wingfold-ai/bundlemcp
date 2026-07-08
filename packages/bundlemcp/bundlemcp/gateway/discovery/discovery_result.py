from dataclasses import dataclass


@dataclass
class DiscoveryResult:
    discovered: int = 0
    changed: int = 0
    error: str | None = None
