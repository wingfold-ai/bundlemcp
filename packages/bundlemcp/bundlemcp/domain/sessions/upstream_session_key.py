import hashlib
import json
from collections.abc import Mapping
from typing import Self

from pydantic import BaseModel, ConfigDict, Field

from bundlemcp.domain.servers.mcp_server import McpServer

SHARED_IDENTITY = "shared"


class UpstreamSessionKey(BaseModel):
    """Which requests one upstream session may serve.

    A session is reused only for a request with an equal key: the same server
    under the same configuration, and the same caller identity unless the
    server is identity-free.
    """

    model_config = ConfigDict(frozen=True)

    server_name: str = Field(description="Upstream server the session is with")
    config_fingerprint: str = Field(
        description="Digest of the server configuration the session was opened under"
    )
    identity_key: str = Field(
        description="'shared' for an identity-free server; otherwise a digest of the caller's "
        "subject and of everything sent on the caller's behalf"
    )

    @classmethod
    def for_request(
        cls,
        server: McpServer,
        *,
        sub: str,
        forwarded_headers: Mapping[str, str],
        endpoint: str,
    ) -> Self:
        """The key of a request ``sub`` makes to ``server`` through ``endpoint``.

        ``forwarded_headers`` are the caller-specific headers the request
        carries, which enter only the digest: the same caller presenting other
        credentials gets another session. A delegated token is minted per
        endpoint, so the endpoint is part of the identity for such a server.
        """
        if server.is_identity_free:
            return cls(
                server_name=server.name,
                config_fingerprint=server.config_fingerprint,
                identity_key=SHARED_IDENTITY,
            )
        material = {
            "sub": sub,
            "headers": sorted((name.lower(), value) for name, value in forwarded_headers.items()),
            "endpoint": endpoint if server.uses_delegated_token else None,
        }
        return cls(
            server_name=server.name,
            config_fingerprint=server.config_fingerprint,
            identity_key=hashlib.sha256(json.dumps(material, sort_keys=True).encode()).hexdigest(),
        )

    @property
    def is_shared(self) -> bool:
        """Whether any caller's request may be served by a session under this key."""
        return self.identity_key == SHARED_IDENTITY

