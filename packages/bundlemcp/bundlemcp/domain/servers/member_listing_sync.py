"""Reconciling a probed listing with the stored one."""

import hashlib
import json
import uuid
from datetime import datetime

from bundlemcp.domain.servers.member_listing import MemberListing
from bundlemcp.domain.servers.probed_listing import ProbedListing


def listing_hash(probed: ProbedListing) -> str:
    canonical = json.dumps(
        {"entries": probed.entries, "scope": probed.cache_scope, "complete": probed.complete},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def sync_member_listing(
    server_id: uuid.UUID, stored: MemberListing | None, probed: ProbedListing, now: datetime
) -> MemberListing | None:
    """The listing to write after a probe, or None when it is what is stored."""
    digest = listing_hash(probed)
    if stored is not None and stored.listing_hash == digest:
        return None
    listing = stored or MemberListing(
        server_id=server_id, kind=probed.kind, listing_hash=digest, listed_at=now
    )
    listing.entries = probed.entries
    listing.cache_scope = probed.cache_scope
    listing.complete = probed.complete
    listing.listing_hash = digest
    listing.listed_at = now
    return listing
