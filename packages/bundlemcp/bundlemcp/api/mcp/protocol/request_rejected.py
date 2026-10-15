from fastapi import Response

from bundlemcp.api.mcp.protocol.cors_grant import CorsGrant


class RequestRejected(Exception):
    """Admission failed; the response to send instead of serving the request.

    ``cors`` is the grant decided before the rejection, so a browser on an
    allowed origin can read, say, a 401 challenge; a rejection raised before the
    endpoint is known carries none.
    """

    def __init__(self, response: Response, cors: CorsGrant | None = None) -> None:
        self.response = response
        self.cors = cors or CorsGrant()
        super().__init__(response.status_code)

    @property
    def answer(self) -> Response:
        """The rejection's response with its CORS headers."""
        return self.cors.apply(self.response)
