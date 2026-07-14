from enum import StrEnum


class AuditStatus(StrEnum):
    SUCCESS = "success"
    ERROR = "error"
    DENIED = "denied"
