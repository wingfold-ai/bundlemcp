from typing import Literal

from pydantic import BaseModel


class CancelSignal(BaseModel):
    type: Literal["cancel"] = "cancel"
    session_id: str
    request_id: str
