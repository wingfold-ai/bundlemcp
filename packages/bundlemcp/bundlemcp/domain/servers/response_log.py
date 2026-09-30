from pydantic import BaseModel, Field

from bundlemcp.domain.servers.observed_response import ObservedResponse


class ResponseLog(BaseModel):
    """The unusable HTTP responses one upstream connection received, in order.

    Created by whoever opens the connection and filled by the transport, so
    the caller can tell a refused credential from an unreachable host after
    the MCP client has reduced both to the same error.
    """

    responses: list[ObservedResponse] = Field(
        default_factory=list, description="Every unusable response, oldest first"
    )

    def record(self, response: ObservedResponse) -> None:
        self.responses.append(response)

    @property
    def last(self) -> ObservedResponse | None:
        return self.responses[-1] if self.responses else None

    @property
    def saw_unauthorized(self) -> bool:
        """The upstream answered 401: the credential was missing, expired or revoked."""
        return any(response.status == 401 for response in self.responses)

    @property
    def insufficient_scope(self) -> ObservedResponse | None:
        """The upstream's 403 insufficient_scope challenge, when it sent one."""
        for response in reversed(self.responses):
            if response.status == 403 and response.challenge.is_insufficient_scope:
                return response
        return None
