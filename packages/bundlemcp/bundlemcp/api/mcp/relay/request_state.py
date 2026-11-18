"""The opaque state a stateless client echoes back when it retries with input."""

# sealed so any replica can resume the call the state describes.

import hashlib
import json
import time
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, ValidationError

from bundlemcp.application.contracts.secret_cipher import DecryptionError, SecretCipher

RelayMode = Literal["parked", "passthrough"]
"""How a call that asked the client for input continues: 'parked' waits on a replica for the
answers; 'passthrough' re-issues the call with them, the upstream holding no state."""


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
    mode: RelayMode = Field(
        description="'parked': the upstream call waits on this replica set for the client's "
        "answers; 'passthrough': the upstream itself asked and holds no state, the retry "
        "re-issues the call with the answers"
    )
    method: str = Field(
        default="tools/call",
        description="The method the state was issued for: 'tools/call', 'prompts/get' or "
        "'resources/read'",
    )
    # states sealed before reads were bridged name the target presented_tool
    target: str = Field(
        validation_alias=AliasChoices("target", "presented_tool"),
        description="What the first request named: the presented tool or prompt name, or the "
        "resource URI",
    )
    arguments_digest: str = Field(description="Digest of the first request's arguments")
    sub: str | None = Field(description="Caller the state was issued to")
    idempotency_key: str | None = Field(
        default=None,
        description="Metering key of a tool call's invocation, so its later legs are charged "
        "once; None for a read, which is not metered",
    )
    member: str | None = Field(
        default=None,
        description="The member that asked for input in passthrough mode on a read, which the "
        "retry goes back to; None for a tool call, whose tool names its server",
    )
    expires_at: float = Field(description="Unix time after which the state is refused")
    upstream_state: str | None = Field(
        default=None,
        description="The upstream's own requestState in passthrough mode, echoed on retry",
    )

    def seal(self, cipher: SecretCipher) -> str:
        return cipher.encrypt(self.model_dump_json())

    @classmethod
    def unseal(
        cls,
        cipher: SecretCipher,
        token: str,
        *,
        method: str,
        target: str,
        arguments: dict[str, Any],
        sub: str | None,
    ) -> RequestState:
        try:
            state = cls.model_validate_json(cipher.decrypt(token))
        except (DecryptionError, ValidationError, ValueError) as exc:
            raise StateRejected("requestState is not valid") from exc
        if state.expires_at < time.time():
            raise StateRejected("requestState has expired")
        if state.sub != sub:
            raise StateRejected("requestState belongs to another caller")
        if (
            state.method != method
            or state.target != target
            or state.arguments_digest != arguments_digest(arguments)
        ):
            raise StateRejected("requestState belongs to a different call")
        return state
