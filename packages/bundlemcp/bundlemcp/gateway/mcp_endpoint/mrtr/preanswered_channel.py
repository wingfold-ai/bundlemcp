"""Answer an upstream's requests from the answers a retry already carries (PROT-18 re-run)."""

from typing import Any

from bundlemcp.gateway.mcp_endpoint.mrtr.relay_rejected import RelayRejected

# Which answer shape belongs to which request kind.
ANSWER_KEYS = {
    "elicitation/create": "action",
    "sampling/createMessage": "role",
    "roots/list": "roots",
}


class PreansweredChannel:
    """Used when the parked call is gone and the call is re-run from the start.

    Each request the upstream repeats is answered with the next unused answer
    of the matching kind; a request with no answer left is refused, which ends
    the upstream call with an error rather than a hang.
    """

    def __init__(self, responses: dict[str, dict[str, Any]]) -> None:
        self._unused = list(responses.values())

    async def ask(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        marker = ANSWER_KEYS.get(method)
        for index, answer in enumerate(self._unused):
            if marker is not None and marker in answer:
                return self._unused.pop(index)
        raise RelayRejected(f"no answer was supplied for {method}")
