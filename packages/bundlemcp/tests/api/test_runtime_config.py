"""Runtime config tests (the Config entity, SES-17/18/19/20)."""

import asyncio

import pytest
from bundlemcp.application.serving.runtime_config import RuntimeConfig
from bundlemcp.domain.config.unknown_config_key import UnknownConfigKey
from bundlemcp.infrastructure.postgres.engine import session_factory
from bundlemcp.infrastructure.postgres.sqlalchemy_unit_of_work import SqlAlchemyUnitOfWorkFactory
from bundlemcp.main.app import create_app
from bundlemcp.main.composition_overrides import CompositionOverrides
from fakeredis.aioredis import FakeRedis
from httpx import ASGITransport, AsyncClient

from tests.conftest import SERVICE_KEY, hermetic_settings, seed_api_key


def _app(engine, redis):
    return create_app(
        hermetic_settings(), overrides=CompositionOverrides(engine=engine, redis=redis)
    )


async def test_defaults_served(engine, redis):
    rc = RuntimeConfig(SqlAlchemyUnitOfWorkFactory(session_factory(engine), redis))
    assert await rc.get("call_timeout") == 60.0
    assert await rc.get("reset_timeout_on_progress") is True
    with pytest.raises(UnknownConfigKey):
        await rc.get("nonsense")


async def test_put_validates_and_overrides(service_client):
    http = service_client
    bad = await http.put("/api/v1/config/call_timeout", json={"value": "fast"})
    assert bad.status_code == 422
    unknown = await http.put("/api/v1/config/nope", json={"value": 1})
    assert unknown.status_code == 404

    ok = await http.put("/api/v1/config/call_timeout", json={"value": 120})
    assert ok.status_code == 200

    effective = (await http.get("/api/v1/config")).json()
    assert effective["call_timeout"] == 120
    assert effective["max_total_timeout"] == 1800.0  # default intact

    # delete resets to default
    await http.request("DELETE", "/api/v1/config/call_timeout")
    effective = (await http.get("/api/v1/config")).json()
    assert effective["call_timeout"] == 60.0


async def test_cross_instance_invalidation(engine, redis: FakeRedis):
    """SES-19/SES-20: a PUT on replica A takes effect on replica B via events, not TTL."""
    await seed_api_key(engine, SERVICE_KEY)
    app_a = _app(engine, redis)
    app_b = _app(engine, redis)

    async with AsyncClient(
        transport=ASGITransport(app=app_a),
        base_url="http://a",
        headers={"Authorization": f"Bearer {SERVICE_KEY}"},
    ) as http_a:
        async with app_a.router.lifespan_context(app_a), app_b.router.lifespan_context(app_b):
            rc_b: RuntimeConfig = app_b.state.container.runtime_config
            assert await rc_b.get("call_timeout") == 60.0  # cached on B

            resp = await http_a.put("/api/v1/config/call_timeout", json={"value": 90})
            assert resp.status_code == 200

            # B's cache must be flushed by the invalidation event (SES-19 budget)
            for _ in range(50):
                if await rc_b.get("call_timeout") == 90.0:
                    break
                await asyncio.sleep(0.05)
            assert await rc_b.get("call_timeout") == 90.0
