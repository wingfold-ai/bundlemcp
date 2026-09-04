from fastapi import Response


class RequestRejected(Exception):
    """Admission failed; the response to send instead of serving the request."""

    def __init__(self, response: Response) -> None:
        self.response = response
        super().__init__(response.status_code)
