class NeedsConnect(Exception):
    """No usable token for (server, user); the caller must (re)connect."""

    def __init__(self, server_name: str, reason: str = "not_connected") -> None:
        self.server_name = server_name
        self.reason = reason
        super().__init__(f"{server_name}: {reason}")
