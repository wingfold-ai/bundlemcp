import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ServerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    url: str
    # SRV-3: header VALUES are write-only; only key names leave the API.
    static_header_names: list[str] = []
    forward_headers: dict[str, str]
    auth_mode: str
    identity_mode: str
    send_identity_header: bool
    capabilities: dict = {}  # DISC-6 advertised-capability snapshot (PROT-11)
    health_status: str
    last_error: str | None
    created_at: datetime
    updated_at: datetime
