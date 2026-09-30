from pydantic import BaseModel, ConfigDict, Field

from bundlemcp.domain.upstream_oauth.upstream_challenge import UpstreamChallenge


class ObservedResponse(BaseModel):
    """An HTTP response from an upstream the MCP client could not use.

    That is any non-2xx answer, or a 2xx whose body is neither JSON nor an
    event stream (a web page served at the URL). The MCP client reports all of
    these as the same generic error, so the status and headers are recorded
    where the HTTP exchange happens.
    """

    model_config = ConfigDict(frozen=True)

    status: int = Field(description="HTTP status code of the response")
    content_type: str = Field(default="", description="Media type of the response, lower-cased")
    challenge: UpstreamChallenge = Field(
        default_factory=UpstreamChallenge,
        description="What its WWW-Authenticate header said, empty when it had none",
    )

    @property
    def is_auth_refusal(self) -> bool:
        return self.status in (401, 403)

    @property
    def carries_jsonrpc(self) -> bool:
        """A JSON body: a modern server's JSON-RPC error rather than a foreign 4xx page."""
        return self.content_type.startswith("application/json")
