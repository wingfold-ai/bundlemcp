"""bundlemcp as an OAuth *client* to protected upstream MCP servers.

Discovery + pre-registered client, encrypted per-(server,user) token storage,
and proactive-expiry refresh with a Redis single-flight lock.
The IdP interaction is behind UpstreamOAuthProvider so hermetic tests inject a
fake instead of reaching a real authorization server.
"""

from bundlemcp.oauth.upstream_client.httpx_upstream_provider import HttpxUpstreamProvider
from bundlemcp.oauth.upstream_client.needs_connect import NeedsConnect
from bundlemcp.oauth.upstream_client.upstream_metadata import UpstreamMetadata
from bundlemcp.oauth.upstream_client.upstream_oauth_not_configured import (
    UpstreamOAuthNotConfigured,
)
from bundlemcp.oauth.upstream_client.upstream_oauth_provider import UpstreamOAuthProvider
from bundlemcp.oauth.upstream_client.upstream_token_store import (
    REFRESH_LOCK_KEY,
    REFRESH_LOCK_TTL,
    REFRESH_SKEW,
    UpstreamTokenStore,
)
from bundlemcp.oauth.upstream_client.upstream_tokens import UpstreamTokens

__all__ = [
    "REFRESH_LOCK_KEY",
    "REFRESH_LOCK_TTL",
    "REFRESH_SKEW",
    "HttpxUpstreamProvider",
    "NeedsConnect",
    "UpstreamMetadata",
    "UpstreamOAuthNotConfigured",
    "UpstreamOAuthProvider",
    "UpstreamTokenStore",
    "UpstreamTokens",
]
