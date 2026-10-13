from typing import Any

from pydantic import BaseModel, Field


class ServerJsonImport(BaseModel):
    """Body for POST /upstreams:from-server-json."""

    document: dict[str, Any] = Field(
        description="An MCP Registry server.json document, as published by the server's author"
    )
