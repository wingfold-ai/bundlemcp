from enum import StrEnum


class CallStatus(StrEnum):
    SUCCESS = "success"
    ERROR = "error"
    INPUT_REQUIRED = "input_required"
