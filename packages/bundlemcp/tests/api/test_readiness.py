"""Readiness names what is missing, and is never an unhandled error (OPS-10, DEP-4)."""

from bundlemcp.infrastructure.postgres.shipped_migrations import ShippedMigrations
from redis.exceptions import ConnectionError as StoreConnectionError

from tests.api.test_gateway import _running
from tests.api.test_store_outage import database_down
from tests.conftest import stamp_head


async def test_ops10_ready_with_both_stores_up_and_the_schema_current(engine, redis):
    """OPS-10: both stores answer and the schema is at the head: 200 ready."""
    async with _running(engine, redis) as (http, _app):
        resp = await http.get("/readyz")
    assert resp.status_code == 200 and resp.json() == {"status": "ready"}


async def test_ops10_postgres_down_is_503(engine, redis):
    """OPS-10: an unreachable Postgres is 503 naming postgres, never 500."""
    async with _running(engine, redis) as (http, _app):
        with database_down(engine):
            resp = await http.get("/readyz")
    assert resp.status_code == 503
    assert resp.json()["failing"] == ["postgres", "migrations"]


async def test_ops10_valkey_down_is_503(engine, redis, monkeypatch):
    """OPS-10: an unreachable Valkey is 503 naming valkey."""

    async def refuse():
        raise StoreConnectionError("connection refused")

    async with _running(engine, redis) as (http, _app):
        monkeypatch.setattr(redis, "ping", refuse)
        resp = await http.get("/readyz")
    assert resp.status_code == 503
    body = resp.json()
    assert body["failing"] == ["valkey"]
    assert "refused" not in body["checks"]["valkey"]["reason"]  # the type, not the message


async def test_dep4_readyz_false_until_schema_current(engine, redis):
    """DEP-4: a database at an older revision is not ready, naming migrations."""
    migrations = ShippedMigrations.read()
    older = next(revision for revision in migrations.known if revision != migrations.head)
    async with _running(engine, redis) as (http, _app):
        await stamp_head(engine, older)
        behind = await http.get("/readyz")
        await stamp_head(engine)
        current = await http.get("/readyz")
    assert behind.status_code == 503 and behind.json()["failing"] == ["migrations"]
    assert migrations.head in behind.json()["checks"]["migrations"]["reason"]
    assert current.status_code == 200


async def test_dep4_a_newer_release_s_schema_counts_as_current(engine, redis):
    """DEP-4: a revision this release does not know is a newer one, and still serves it."""
    async with _running(engine, redis) as (http, _app):
        await stamp_head(engine, "9999_from_a_newer_release")
        resp = await http.get("/readyz")
    assert resp.status_code == 200


def test_dep4_no_revision_at_all_is_behind():
    assert not ShippedMigrations.read().is_current(None)
