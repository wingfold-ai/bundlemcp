"""The CORS answer one MCP request gets, decided once its endpoint is known."""

from fastapi import Response
from pydantic import BaseModel, ConfigDict, Field

MCP_METHODS = "GET, POST, DELETE, OPTIONS"
MCP_REQUEST_HEADERS = (
    "Authorization, Content-Type, Accept, Mcp-Session-Id, MCP-Protocol-Version, Mcp-Method, "
    "Last-Event-ID, X-API-Key"
)
MCP_EXPOSED_HEADERS = "Mcp-Session-Id, WWW-Authenticate"
PREFLIGHT_MAX_AGE_SECONDS = 600


class CorsGrant(BaseModel):
    """The browser origin a response may be read by, or none.

    Credentials are never granted: MCP endpoints authenticate by header, so a
    page can only present tokens it already holds.
    """

    model_config = ConfigDict(frozen=True)

    origin: str | None = Field(
        default=None,
        description="The request's Origin, when the endpoint allows it; None when the request "
        "carried no Origin and needs no grant",
    )

    def apply(self, response: Response) -> Response:
        """``response`` with the CORS headers for the granted origin, if there is one."""
        if self.origin is not None:
            response.headers["Access-Control-Allow-Origin"] = self.origin
            response.headers["Access-Control-Expose-Headers"] = MCP_EXPOSED_HEADERS
            response.headers.append("Vary", "Origin")
        return response

    def preflight(self) -> Response:
        """The answer to a preflight from the granted origin."""
        response = Response(status_code=204)
        response.headers["Access-Control-Allow-Methods"] = MCP_METHODS
        response.headers["Access-Control-Allow-Headers"] = MCP_REQUEST_HEADERS
        response.headers["Access-Control-Max-Age"] = str(PREFLIGHT_MAX_AGE_SECONDS)
        return self.apply(response)
