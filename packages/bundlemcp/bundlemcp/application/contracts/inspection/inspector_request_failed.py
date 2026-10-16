class InspectorRequestFailed(Exception):
    """A target answered an inspector request with a JSON-RPC error."""

    def __init__(self, code: int, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")
