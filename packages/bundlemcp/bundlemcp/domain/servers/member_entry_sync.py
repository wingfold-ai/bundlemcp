"""Reconciling a member's listed prompts or resources with the cached entries."""

import hashlib
import json
import uuid
from datetime import datetime

from bundlemcp.domain.servers.member_entry import MemberEntry
from bundlemcp.domain.servers.member_entry_kind import MemberEntryKind
from bundlemcp.domain.servers.probed_entry import ProbedEntry


def _entry_hash(seen: ProbedEntry) -> str:
    canonical = json.dumps(seen.model_dump(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def sync_member_entries(
    server_id: uuid.UUID,
    kind: MemberEntryKind,
    existing: dict[str, MemberEntry],
    probed: list[ProbedEntry],
    now: datetime,
) -> list[MemberEntry]:
    """The entries to write after a listing: new, changed, vanished or back again.

    Like tools, an entry is written only when its hash moved or its staleness
    changed, and a vanished entry is marked stale rather than deleted, so its
    curation survives a member that briefly stops listing it.
    """
    staged: list[MemberEntry] = []
    for seen in probed:
        digest = _entry_hash(seen)
        row = existing.get(seen.key)
        if row is None:
            staged.append(
                MemberEntry(
                    server_id=server_id,
                    kind=kind,
                    key=seen.key,
                    name=seen.name,
                    title=seen.title,
                    description=seen.description,
                    entry_hash=digest,
                )
            )
            continue
        if row.entry_hash == digest and not row.is_stale:
            continue
        row.name, row.title, row.description = seen.name, seen.title, seen.description
        row.entry_hash = digest
        row.stale_since = None
        staged.append(row)
    listed = {seen.key for seen in probed}
    for key, row in existing.items():
        if key not in listed and not row.is_stale:
            row.stale_since = now
            staged.append(row)
    return staged
