from enum import StrEnum


class NeutralError(StrEnum):
    """An error whose JSON-RPC code depends on the client's protocol revision.

    Handlers raise the condition; the client's dialect chooses the number.
    """

    RESOURCE_NOT_FOUND = "resource_not_found"
    METHOD_NOT_FOUND = "method_not_found"
