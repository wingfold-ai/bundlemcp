"""Runtime config tests (spec 02 Config, STP-1/2/3/4)."""

import asyncio

import pytest
from bundlemcp.api.app import create_app
from bundlemcp.crypto import API_KEY_PREFIX, display_prefix, generate_token, hash_token
from bundlemcp.gateway.runtime_config import RuntimeConfig, UnknownConfigKey
from bundlemcp.models import ApiKey, ApiKeyKind
from bundlemcp.settings import Settings
from bundlemcp.store import session_factory
from fakeredis.aioredis import FakeRedis
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

SERVICE_KEY = generate_token(API_KEY_PREFIX)


async def _seed_service_key(engine: AsyncEngine) -> None:
    async with session_factory(engine)() as db:
        db.add(
            ApiKey(
                name="svc",
                key_hash=hash_token(SERVICE_KEY),
                key_prefix=display_prefix(SERVICE_KEY),
                kind=ApiKeyKind.SERVICE,
            )
        )
        await db.commit()


def _app(engine, redis):
    settings = Settings(_env_file=None, database_url="sqlite+aiosqlite://")
    return create_app(settings, engine=engine, redis=redis)


async def test_defaults_served(engine, redis):
    rc = RuntimeConfig(session_factory(engine))
    assert await rc.get("call_timeout") == 60.0
    assert await rc.get("reset_timeout_on_progress") is True
    with pytest.raises(UnknownConfigKey):
        await rc.get("nonsense")


async def test_put_validates_and_overrides(engine, redis):
    await _seed_service_key(engine)
    app = _app(engine, redis)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://t",
        headers={"Authorization": f"Bearer {SERVICE_KEY}"},
    ) as http:
        async with app.router.lifespan_context(app):
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
    """STP-3/STP-4: a PUT on replica A takes effect on replica B via events, not TTL."""
    await _seed_service_key(engine)
    app_a = _app(engine, redis)
    app_b = _app(engine, redis)

    async with AsyncClient(
        transport=ASGITransport(app=app_a),
        base_url="http://a",
        headers={"Authorization": f"Bearer {SERVICE_KEY}"},
    ) as http_a:
        async with app_a.router.lifespan_context(app_a), app_b.router.lifespan_context(app_b):
            rc_b: RuntimeConfig = app_b.state.runtime_config
            assert await rc_b.get("call_timeout") == 60.0  # cached on B

            resp = await http_a.put("/api/v1/config/call_timeout", json={"value": 90})
            assert resp.status_code == 200

            # B's cache must be flushed by the invalidation event (STP-3 budget)
            for _ in range(50):
                if await rc_b.get("call_timeout") == 90.0:
                    break
                await asyncio.sleep(0.05)
            assert await rc_b.get("call_timeout") == 90.0
