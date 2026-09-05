from enum import StrEnum


class AuditStatus(StrEnum):
    SUCCESS = "success"
    ERROR = "error"
    DENIED = "denied"
    INPUT_REQUIRED = "input_required"
