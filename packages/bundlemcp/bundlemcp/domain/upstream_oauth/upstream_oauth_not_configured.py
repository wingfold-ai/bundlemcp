class UpstreamOAuthNotConfigured(Exception):
    """A server needs upstream OAuth but this gateway has no token encryption keys."""

    def __init__(self, server_name: str) -> None:
        self.server_name = server_name
        super().__init__(f"{server_name}: upstream OAuth not configured on this gateway")
