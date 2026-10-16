from pydantic import BaseModel, Field

from bundlemcp.domain.sessions.upstream_session_key import UpstreamSessionKey


class UpstreamBinding(BaseModel):
    """A session's attachment to the one upstream session that serves it on a server.

    Holds what any replica needs to continue that upstream session; header
    values are never part of it, only digests.
    """

    server_name: str = Field(description="Upstream server this binding is for")
    upstream_session_id: str | None = Field(
        default=None,
        description="Session id the upstream issued; null for an upstream that has no sessions",
    )
    identity_key: str | None = Field(
        default=None,
        description="Identity part of the upstream session key the binding was made under: "
        "'shared' or a digest of the caller's identity, never a header value",
    )
    protocol_version: str | None = Field(
        default=None,
        description="MCP revision the upstream session negotiated, sent again when it is "
        "continued without initialize",
    )
    config_fingerprint: str | None = Field(
        default=None,
        description="Digest of the server configuration the upstream session was opened under; "
        "a binding made under another configuration is re-established, not reused",
    )

    def continues(self, key: UpstreamSessionKey) -> bool:
        """Whether the bound upstream session may serve a request under ``key``.

        Only a session the upstream identified can be continued, and only under
        the configuration and identity it was opened with.
        """
        return (
            self.upstream_session_id is not None
            and self.server_name == key.server_name
            and self.config_fingerprint == key.config_fingerprint
            and self.identity_key == key.identity_key
        )
