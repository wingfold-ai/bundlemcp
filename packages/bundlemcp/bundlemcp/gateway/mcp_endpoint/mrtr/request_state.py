"""The opaque state a modern client echoes back when it retries with input (PROT-18)."""

import hashlib
import json
import time
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from bundlemcp.crypto import DecryptionError, TokenCipher


class StateRejected(Exception):
    """A requestState that is not ours, not this caller's, not this call's, or expired."""


def arguments_digest(arguments: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(arguments, sort_keys=True, default=str).encode()).hexdigest()


class RequestState(BaseModel):
    """What a retry must prove before it may resume or re-run a call.

    Sealed with the gateway's token cipher, so a client can neither read nor
    forge it; unsealing checks the principal, the call and the expiry.
    """

    model_config = ConfigDict(frozen=True)

    correlation_id: str = Field(description="Key under which the parked call, if any, waits")
    mode: Literal["parked", "passthrough"] = Field(
        description="'parked': the upstream call waits on this replica set for the client's "
        "answers; 'passthrough': the upstream itself asked and holds no state, the retry "
        "re-issues the call with the answers"
    )
    presented_tool: str = Field(description="Tool name the client used on the first request")
    arguments_digest: str = Field(description="Digest of the first request's arguments")
    sub: str | None = Field(description="Caller the state was issued to")
    idempotency_key: str = Field(
        description="Metering key of the client invocation, so a retry is charged once"
    )
    expires_at: float = Field(description="Unix time after which the state is refused")
    upstream_state: str | None = Field(
        default=None,
        description="The upstream's own requestState in passthrough mode, echoed on retry",
    )

    def seal(self, cipher: TokenCipher) -> str:
        return cipher.encrypt(self.model_dump_json())

    @classmethod
    def unseal(
        cls,
        cipher: TokenCipher,
        token: str,
        *,
        presented_tool: str,
        arguments: dict[str, Any],
        sub: str | None,
    ) -> "RequestState":
        try:
            state = cls.model_validate_json(cipher.decrypt(token))
        except (DecryptionError, ValidationError, ValueError) as exc:
            raise StateRejected("requestState is not valid") from exc
        if state.expires_at < time.time():
            raise StateRejected("requestState has expired")
        if state.sub != sub:
            raise StateRejected("requestState belongs to another caller")
        if state.presented_tool != presented_tool or state.arguments_digest != arguments_digest(
            arguments
        ):
            raise StateRejected("requestState belongs to a different call")
        return state
