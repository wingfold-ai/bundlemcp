"""Storing members' listing snapshots (UPS-24) and the migration that adds them (UPS-38)."""

import importlib
import uuid

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from bundlemcp.domain.servers.listing_kind import ListingKind
from bundlemcp.domain.servers.member_listing import MemberListing
from bundlemcp.domain.shared.clock import utcnow
from bundlemcp.infrastructure.postgres.member_listing_repository import (
    SqlAlchemyMemberListingRepository,
)
from bundlemcp.infrastructure.postgres.rows.mcp_server_row import McpServerRow
from bundlemcp.infrastructure.postgres.rows.member_listing_row import MemberListingRow
from sqlmodel import select

revision = importlib.import_module(
    "bundlemcp.infrastructure.postgres.migrations.versions.0016_member_listings"
)


async def test_ups24_listing_round_trips_and_cascades(db):
    """UPS-24: a stored listing reads back entry for entry, in order, and goes with its server."""
    server = McpServerRow(name="docs", url="http://docs:8000/mcp")
    db.add(server)
    await db.commit()
    repo = SqlAlchemyMemberListingRepository(db)
    entries = [{"uri": "file:///b", "mimeType": "text/plain"}, {"uri": "file:///a"}]
    repo.add(
        MemberListing(
            server_id=server.id,
            kind=ListingKind.RESOURCES,
            entries=entries,
            cache_scope="public",
            listing_hash="h",
            listed_at=utcnow(),
        )
    )
    await db.commit()

    (stored,) = await repo.for_servers([server.id], ListingKind.RESOURCES)
    assert stored.entries == entries
    assert stored.cache_scope == "public" and stored.complete
    assert await repo.for_servers([server.id], ListingKind.PROMPTS) == []

    await db.delete(server)
    await db.commit()
    assert (await db.execute(select(MemberListingRow))).scalars().all() == []


def _run(conn: sa.Connection, step) -> None:
    with Operations.context(MigrationContext.configure(conn)):
        step()


def test_ups38_upgrade_defaults_existing_servers_to_auto_and_downgrade_drops():
    """UPS-38: servers stored before the upgrade read as 'auto'; the downgrade removes both
    the column and the table."""
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE mcp_servers (id CHAR(32) PRIMARY KEY)"))
        conn.execute(sa.text("INSERT INTO mcp_servers VALUES (:id)"), {"id": uuid.uuid4().hex})

        _run(conn, revision.upgrade)
        modes = conn.execute(sa.text("SELECT listing_snapshot FROM mcp_servers")).scalars().all()
        assert modes == ["auto"]
        assert "member_listings" in sa.inspect(conn).get_table_names()

        _run(conn, revision.downgrade)
        columns = {c["name"] for c in sa.inspect(conn).get_columns("mcp_servers")}
        assert columns == {"id"}
        assert "member_listings" not in sa.inspect(conn).get_table_names()
