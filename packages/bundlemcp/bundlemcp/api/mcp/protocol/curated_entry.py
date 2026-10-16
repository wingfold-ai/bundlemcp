from typing import Any

from bundlemcp.domain.bundles.member_entry_curation import MemberEntryCuration


def curated_entry(
    curation: MemberEntryCuration | None, entry: dict[str, Any]
) -> dict[str, Any] | None:
    """A member's prompt or resource entry as the bundle presents it; None when it is hidden.

    Only the title and description are ever replaced; names, URIs and arguments
    stay as the member listed them.
    """
    if curation is None:
        return entry
    if not curation.enabled:
        return None
    if curation.override_title is not None:
        entry["title"] = curation.override_title
    if curation.override_description is not None:
        entry["description"] = curation.override_description
    return entry
