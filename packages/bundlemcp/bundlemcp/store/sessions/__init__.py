"""Session records in Redis: a session is data, not an object.

Records are JSON values under SESSION_KEY with a TTL; any replica loads/serves
them. Updates go through optimistic check-and-set.
"""

from bundlemcp.store.sessions._common import SESSION_RECORD_VERSION
from bundlemcp.store.sessions.session_record import SessionRecord
from bundlemcp.store.sessions.session_store import SessionStore
from bundlemcp.store.sessions.upstream_binding import UpstreamBinding

__all__ = [
    "SESSION_RECORD_VERSION",
    "SessionRecord",
    "SessionStore",
    "UpstreamBinding",
]
