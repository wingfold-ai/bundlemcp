from enum import StrEnum


class HealthStatus(StrEnum):
    OK = "ok"
    ERROR = "error"
    UNKNOWN = "unknown"
