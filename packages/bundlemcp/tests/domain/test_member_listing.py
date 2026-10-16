"""When a member's listing snapshot may be served to every caller (UPS-38) and how it syncs."""

import uuid
from datetime import UTC, datetime
from typing import Literal

from bundlemcp.domain.servers.listing_kind import ListingKind
from bundlemcp.domain.servers.listing_snapshot_mode import ListingSnapshotMode
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.servers.member_listing import MemberListing
from bundlemcp.domain.servers.member_listing_sync import sync_member_listing
from bundlemcp.domain.servers.probed_listing import ProbedListing

SERVER = uuid.uuid4()
FIRST = datetime(2026, 10, 1, tzinfo=UTC)
LATER = datetime(2026, 10, 2, tzinfo=UTC)

FREE = McpServer(name="echo", url="https://echo.example/mcp", send_identity_header=False)
FORWARDING = McpServer(
    name="crm",
    url="https://crm.example/mcp",
    forward_headers={"authorization": "authorization"},
    send_identity_header=False,
)
IDENTIFIED = McpServer(name="wiki", url="http://wiki:8080/mcp", send_identity_header=True)


def _listing(
    scope: Literal["public", "private"] | None = None, *, complete: bool = True
) -> MemberListing:
    probed = ProbedListing(
        kind=ListingKind.PROMPTS,
        entries=[{"name": "daily"}] if complete else [],
        cache_scope=scope,
        complete=complete,
    )
    listing = sync_member_listing(SERVER, None, probed, FIRST)
    assert listing is not None
    return listing


def test_ups38_identity_free_listing_shared():
    """UPS-38: an unscoped listing of a server sent nothing caller-specific is shareable."""
    assert _listing().shareable_for(FREE)


def test_ups38_identity_bearing_listing_not_shared():
    """UPS-38: under auto, an unscoped listing of a server that forwards caller headers, or is
    sent the caller's identity, is not shareable."""
    assert not _listing().shareable_for(FORWARDING)
    assert not _listing().shareable_for(IDENTIFIED)


def test_ups38_server_scope_decides():
    """UPS-38: under auto, the server's own cacheScope wins over the identity rule."""
    assert _listing("public").shareable_for(FORWARDING)
    assert not _listing("private").shareable_for(FREE)


def test_ups38_operator_shares_or_refuses():
    """UPS-38: 'shared' shares an identified server's listing even when marked private, and
    'live' shares nothing."""
    shared = IDENTIFIED.model_copy(update={"listing_snapshot": ListingSnapshotMode.SHARED})
    live = FREE.model_copy(update={"listing_snapshot": ListingSnapshotMode.LIVE})
    assert _listing().shareable_for(shared)
    assert _listing("private").shareable_for(shared)
    assert not _listing("public").shareable_for(live)


def test_ups38_incomplete_listing_never_shared():
    """UPS-38: a listing cut at the bound is not served, whatever the setting."""
    shared = FREE.model_copy(update={"listing_snapshot": ListingSnapshotMode.SHARED})
    assert not _listing("public", complete=False).shareable_for(shared)


def test_ups24_unchanged_listing_writes_nothing():
    """UPS-24: a probe that reads the stored listing again stages no write."""
    stored = _listing()
    probed = ProbedListing(kind=ListingKind.PROMPTS, entries=[{"name": "daily"}])
    assert sync_member_listing(SERVER, stored, probed, LATER) is None


def test_ups24_changed_listing_rewrites_the_row():
    """UPS-24: a changed listing updates the stored row in place, in the server's order."""
    stored = _listing()
    probed = ProbedListing(
        kind=ListingKind.PROMPTS, entries=[{"name": "weekly"}, {"name": "daily"}]
    )
    written = sync_member_listing(SERVER, stored, probed, LATER)
    assert written is not None and written.id == stored.id
    assert [e["name"] for e in written.entries] == ["weekly", "daily"]
    assert written.listed_at == LATER
