from pydantic import Field

from bundlemcp.api.mcp.protocol.request_context import RequestContext
from bundlemcp.domain.sessions.session_record import SessionRecord


class SessionRequestContext(RequestContext):
    """A request admitted into a handshake session, which it always names.

    Code that only serves the session era takes this type, so it reads the
    session without narrowing it; handlers keep taking ``RequestContext`` and
    stay unaware of the era.
    """

    session: SessionRecord = Field(
        description="The handshake session the request belongs to, loaded from the session store"
    )
