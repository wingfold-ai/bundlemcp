from typing import Any, Literal

from pydantic import BaseModel


class ReplySignal(BaseModel):
    type: Literal["reply"] = "reply"
    correlation_id: str
    payload: dict[str, Any]
