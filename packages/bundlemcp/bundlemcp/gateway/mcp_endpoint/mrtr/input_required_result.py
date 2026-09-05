from typing import Any


def input_required_result(
    requests: dict[str, dict[str, Any]], request_state: str
) -> dict[str, Any]:
    """The interim result that asks a modern client for input before the call can finish."""
    return {
        "resultType": "input_required",
        "inputRequests": requests,
        "requestState": request_state,
    }
