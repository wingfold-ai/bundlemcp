import secrets


def new_session_id() -> str:
    """An unguessable id for a handshake-era session."""
    return secrets.token_urlsafe(24)
