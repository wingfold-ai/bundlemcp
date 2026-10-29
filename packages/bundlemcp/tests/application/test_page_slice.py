"""The typed page a repository returns in place of a ``(total, rows)`` tuple."""

from bundlemcp.application.contracts.persistence.page_slice import PageSlice
from bundlemcp.application.schemas.common.page import Page
from bundlemcp.domain.access.user import User


def test_mgmt5_a_page_slice_keeps_entities_unrevalidated() -> None:
    """MGMT-5: a slice hands back the very entity instances it was built from."""
    users = [User(oidc_issuer="i", oidc_sub=str(n)) for n in range(3)]

    page_slice = PageSlice[User](items=users, total=7)

    assert page_slice.total == 7
    assert all(got is want for got, want in zip(page_slice.items, users, strict=True))


def test_mgmt5_page_of_renders_a_slice_with_its_window() -> None:
    """MGMT-5: the published envelope carries the slice's rows, total, offset and limit."""
    users = [User(oidc_issuer="i", oidc_sub=str(n)) for n in range(2)]

    page = Page[str].of(
        PageSlice[User](items=users, total=9), offset=4, limit=2, read=lambda u: u.oidc_sub
    )

    assert page.model_dump() == {"items": ["0", "1"], "total": 9, "offset": 4, "limit": 2}
