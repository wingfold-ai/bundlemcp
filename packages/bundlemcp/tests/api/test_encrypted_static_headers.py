"""Static headers encrypted at rest still reach the upstream (ARC-18)."""

import json

from cryptography.fernet import Fernet
from sqlalchemy import text

from tests.api.test_upstream_session_pooling import _call, _echo, _initialize, _seed
from tests.conftest import ENDPOINT_KEY, SERVICE_KEY, hermetic_settings, seed_api_key, serving
from tests.loopback_upstream import RecordingUpstream, serving_upstream


async def test_arc18_encrypted_header_reaches_upstream(engine, redis):
    """ARC-18: a header set through the management API on a gateway with a key is stored as
    ciphertext only, and a tool call still sends it upstream."""
    recording = RecordingUpstream(_echo())
    settings = hermetic_settings(
        egress_allow_cidrs=["127.0.0.1/32"],
        discovery_refresh_interval=0,
        token_encryption_keys=[Fernet.generate_key().decode()],
    )
    async with serving_upstream(recording) as url:
        await _seed(engine, url)
        await seed_api_key(engine, SERVICE_KEY, name="svc")
        async with serving(engine, redis, settings=settings, bearer=SERVICE_KEY) as (admin, _):
            resp = await admin.put(
                "/api/v1/upstreams/echo",
                json={
                    "name": "echo",
                    "url": url,
                    "protocol_mode": "legacy",
                    "static_headers": {"Authorization": "Bearer s3cret"},
                },
            )
            assert resp.status_code == 200, resp.text
            assert "s3cret" not in resp.text
        async with engine.connect() as conn:
            plaintext, ciphertext = (
                await conn.execute(
                    text(
                        "SELECT static_headers, static_headers_encrypted FROM mcp_servers "
                        "WHERE name = 'echo'"
                    )
                )
            ).one()
        assert json.loads(plaintext) == {}
        assert ciphertext and "s3cret" not in ciphertext
        async with serving(engine, redis, settings=settings, bearer=ENDPOINT_KEY) as (http, _):
            result = await _call(http, await _initialize(http))
    assert result["result"]["content"][0]["text"] == "said:hi"
    [call] = recording.calls("tools/call")
    assert call.headers.get("authorization") == "Bearer s3cret"
