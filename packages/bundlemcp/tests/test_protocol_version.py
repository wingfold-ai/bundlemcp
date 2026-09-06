"""Handshake-era version negotiation (PROT-12)."""

from bundlemcp.gateway.protocol_version import (
    HANDSHAKE_PROTOCOL_VERSIONS,
    negotiate_handshake_version,
)

NEWEST = HANDSHAKE_PROTOCOL_VERSIONS[0]


def negotiate(requested):
    return negotiate_handshake_version(requested, HANDSHAKE_PROTOCOL_VERSIONS)


def test_blank_request_gets_newest():
    assert negotiate(None) == NEWEST
    assert negotiate("") == NEWEST


def test_exact_supported_version_echoed():
    for v in HANDSHAKE_PROTOCOL_VERSIONS:
        assert negotiate(v) == v


def test_newer_than_known_offers_newest():
    assert negotiate("2099-01-01") == NEWEST


def test_within_window_downgrades_to_newest_supported():
    assert negotiate("2025-07-01") == "2025-06-18"
    assert negotiate("2025-04-01") == "2025-03-26"


def test_older_than_window_fails():
    assert negotiate("2024-11-05") is None


def test_no_supported_versions_fails():
    """With the handshake era switched off there is nothing to negotiate."""
    assert negotiate_handshake_version("2025-11-25", []) is None


def test_version_lists_come_from_the_sdk_newest_first():
    """PROT-22: the served revisions are the SDK's, above the gateway's handshake floor."""
    from bundlemcp.gateway.protocol_version import (
        MODERN_PROTOCOL_VERSIONS,
        OLDEST_HANDSHAKE_SERVED,
    )
    from mcp_types.version import HANDSHAKE_PROTOCOL_VERSIONS as SDK_HANDSHAKE
    from mcp_types.version import MODERN_PROTOCOL_VERSIONS as SDK_MODERN

    assert HANDSHAKE_PROTOCOL_VERSIONS == sorted(HANDSHAKE_PROTOCOL_VERSIONS, reverse=True)
    assert HANDSHAKE_PROTOCOL_VERSIONS[-1] == OLDEST_HANDSHAKE_SERVED
    assert set(HANDSHAKE_PROTOCOL_VERSIONS) < set(SDK_HANDSHAKE)
    assert "2024-11-05" not in HANDSHAKE_PROTOCOL_VERSIONS
    assert MODERN_PROTOCOL_VERSIONS == list(reversed(SDK_MODERN))


def test_dialects_allow_exactly_the_revisions_methods():
    """PROT-8/PROT-13/PROT-17/PROT-20: the method set per revision is the SDK's, not a denylist."""
    from bundlemcp.gateway.dialect import HandshakeDialect, ModernDialect

    handshake = HandshakeDialect("2025-11-25")
    modern = ModernDialect("2026-07-28")
    for method in ("initialize", "ping", "logging/setLevel", "resources/subscribe"):
        assert handshake.allows(method) and not modern.allows(method), method
    for method in ("server/discover", "subscriptions/listen"):
        assert modern.allows(method) and not handshake.allows(method), method
    for method in ("tools/list", "tools/call", "resources/read", "notifications/cancelled"):
        assert modern.allows(method) and handshake.allows(method), method
    assert not modern.allows("made/up") and not handshake.allows("made/up")
