from typing import Any, Literal

from pydantic import BaseModel


class DeliverSignal(BaseModel):
    type: Literal["deliver"] = "deliver"
    session_id: str
    payload: dict[str, Any]
