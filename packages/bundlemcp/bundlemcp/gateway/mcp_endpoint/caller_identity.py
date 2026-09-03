"""The identity string a call is attributed to."""

from bundlemcp.store.sessions import SessionRecord


def caller_sub(record: SessionRecord) -> str | None:
    """The OAuth user, else the API key, else None for an anonymous endpoint."""
    return record.user_id or (f"api_key:{record.api_key_id}" if record.api_key_id else None)
