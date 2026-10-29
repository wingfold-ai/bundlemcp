"""The in-memory and the SQL audit repositories filter and order alike (OPS-6)."""

import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime, timedelta

import pytest
from bundlemcp.application.management.audit_cursor import AuditCursor
from bundlemcp.application.management.audit_filter import AuditFilter
from bundlemcp.domain.access.api_key import ApiKey
from bundlemcp.domain.access.api_key_kind import ApiKeyKind
from bundlemcp.domain.access.user import User
from bundlemcp.domain.audit.audit_kind import AuditKind
from bundlemcp.domain.audit.audit_record import AuditRecord
from bundlemcp.domain.audit.audit_status import AuditStatus
from bundlemcp.infrastructure.memory.in_memory_unit_of_work import InMemoryUnitOfWorkFactory
from bundlemcp.infrastructure.postgres.engine import session_factory
from bundlemcp.infrastructure.postgres.sqlalchemy_unit_of_work import SqlAlchemyUnitOfWorkFactory

NOW = datetime(2026, 10, 29, 12, tzinfo=UTC)
USER = uuid.UUID("00000000-0000-4000-8000-000000000001")
KEY = uuid.UUID("00000000-0000-4000-8000-000000000002")


def _records() -> list[AuditRecord]:
    """Records that each filter field tells apart; two share a timestamp."""
    tie = NOW - timedelta(minutes=5)
    return [
        AuditRecord(
            id=uuid.UUID("10000000-0000-4000-8000-000000000000"),
            created_at=NOW - timedelta(hours=3),
            endpoint_name="main",
            bundle_name="demo",
            server_name="alpha",
            tool_name="search",
            presented_tool_name="alpha_search",
            user_id=USER,
            idempotency_key="inv-1",
            status=AuditStatus.SUCCESS,
        ),
        AuditRecord(
            id=uuid.UUID("20000000-0000-4000-8000-000000000000"),
            created_at=NOW - timedelta(hours=2),
            endpoint_name="side",
            bundle_name="other",
            server_name="beta",
            tool_name="fetch",
            presented_tool_name="beta_fetch",
            api_key_id=KEY,
            idempotency_key="inv-2",
            status=AuditStatus.ERROR,
        ),
        AuditRecord(
            id=uuid.UUID("30000000-0000-4000-8000-000000000000"),
            created_at=tie,
            endpoint_name="main",
            bundle_name="demo",
            server_name="beta",
            tool_name="search",
            presented_tool_name="beta_search",
            api_key_id=KEY,
            status=AuditStatus.DENIED,
        ),
        AuditRecord(
            id=uuid.UUID("f0000000-0000-4000-8000-000000000000"),
            created_at=tie,
            endpoint_name="main",
            bundle_name="demo",
            server_name="alpha",
            tool_name="fetch",
            presented_tool_name="alpha_fetch",
            user_id=USER,
            idempotency_key="inv-1",
            status=AuditStatus.SUCCESS,
        ),
        AuditRecord.management_event(
            "export.secrets_included", user_id=USER, api_key_id=None, auth_method=None
        ).model_copy(
            update={
                "id": uuid.UUID("a0000000-0000-4000-8000-000000000000"),
                "created_at": NOW - timedelta(hours=1),
            }
        ),
    ]


FILTERS: dict[str, AuditFilter] = {
    "none": AuditFilter(),
    "created_from": AuditFilter(created_from=NOW - timedelta(hours=2)),
    "created_to": AuditFilter(created_to=NOW - timedelta(hours=2)),
    "kind": AuditFilter(kind=AuditKind.MANAGEMENT),
    "endpoint_name": AuditFilter(endpoint_name="main"),
    "bundle_name": AuditFilter(bundle_name="other"),
    "server_name": AuditFilter(server_name="alpha"),
    "tool_name_upstream": AuditFilter(tool_name="search"),
    "tool_name_presented": AuditFilter(tool_name="beta_fetch"),
    "user_id": AuditFilter(user_id=USER),
    "api_key_id": AuditFilter(api_key_id=KEY),
    "status": AuditFilter(status=AuditStatus.SUCCESS),
    "idempotency_key": AuditFilter(idempotency_key="inv-1"),
}

Opener = Callable[[], AbstractAsyncContextManager]


@pytest.fixture(params=["memory", "sqlite"])
async def opener(request, engine, redis) -> AsyncIterator[Opener]:
    """A unit-of-work opener of either kind, seeded with the same records."""
    if request.param == "memory":
        units = InMemoryUnitOfWorkFactory()
    else:
        units = SqlAlchemyUnitOfWorkFactory(session_factory(engine), redis)
    async with units.open() as uow:
        uow.users.add(User(id=USER, oidc_issuer="i", oidc_sub="u"))
        uow.api_keys.add(
            ApiKey(id=KEY, name="k", key_hash="h", key_prefix="p", kind=ApiKeyKind.SERVICE)
        )
        await uow.commit()
        for record in _records():
            uow.audit_records.add(record)
        await uow.commit()
    yield units.open


async def _paged(opener: Opener, filter_: AuditFilter) -> list[uuid.UUID]:
    async with opener() as uow:
        rows = (await uow.audit_records.page(filter_, offset=0, limit=100)).items
    return [row.id for row in rows]


async def _walked(opener: Opener, filter_: AuditFilter) -> list[uuid.UUID]:
    """Every id a keyset walk returns, two records at a time."""
    ids: list[uuid.UUID] = []
    cursor: AuditCursor | None = None
    while True:
        async with opener() as uow:
            rows = await uow.audit_records.page_after(filter_, cursor=cursor, limit=2)
        if not rows:
            return ids
        ids.extend(row.id for row in rows)
        cursor = AuditCursor(created_at=rows[-1].created_at, id=rows[-1].id)


def _expected(filter_: AuditFilter) -> list[uuid.UUID]:
    matching = [r for r in _records() if filter_.matches(r)]
    return [r.id for r in sorted(matching, key=lambda r: (r.created_at, r.id), reverse=True)]


@pytest.mark.parametrize("case", list(FILTERS))
async def test_ops6_filters_agree_across_repositories(opener, case):
    """OPS-6: each filter field, and the tool filter on either name, selects the same records
    in the same order from both repositories, through ``page()`` and ``page_after()``."""
    filter_ = FILTERS[case]
    expected = _expected(filter_)
    assert expected, f"filter case {case!r} must select at least one record"
    assert await _paged(opener, filter_) == expected
    assert await _walked(opener, filter_) == expected


async def test_ops6_newest_first_with_ties_broken_by_id(opener):
    """OPS-6: records are listed newest first, and two records stamped at the same instant are
    ordered by id descending, through ``page()`` and ``page_after()`` alike."""
    newest_first = [
        uuid.UUID("f0000000-0000-4000-8000-000000000000"),
        uuid.UUID("30000000-0000-4000-8000-000000000000"),
        uuid.UUID("a0000000-0000-4000-8000-000000000000"),
        uuid.UUID("20000000-0000-4000-8000-000000000000"),
        uuid.UUID("10000000-0000-4000-8000-000000000000"),
    ]
    assert await _paged(opener, AuditFilter()) == newest_first
    assert await _walked(opener, AuditFilter()) == newest_first
