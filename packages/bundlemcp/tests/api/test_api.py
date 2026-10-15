"""Management API tests (MGMT-2/4/5/6; EP-3/EP-8; the auth spec)."""

import pytest
from httpx import AsyncClient


@pytest.fixture
def client(service_client: AsyncClient) -> AsyncClient:
    return service_client


async def test_auth_required(client: AsyncClient):
    """MGMT-2: no credentials -> 401; endpoint-kind key -> 403."""
    resp = await client.get("/api/v1/upstreams", headers={"Authorization": ""})
    assert resp.status_code == 401

    created = await client.post("/api/v1/api-keys", json={"name": "ep-key", "kind": "endpoint"})
    ep_key = created.json()["key"]
    resp = await client.get("/api/v1/upstreams", headers={"Authorization": f"Bearer {ep_key}"})
    assert resp.status_code == 403


async def test_server_upsert_idempotent(client: AsyncClient):
    """MGMT-4: PUT create-or-update by name, tolerates transport field, idempotent."""
    body = {"name": "seo", "url": "http://seo:8000/mcp", "transport": "streamable-http"}
    r1 = await client.put("/api/v1/upstreams/seo", json=body)
    assert r1.status_code == 200
    r2 = await client.put("/api/v1/upstreams/seo", json=body)
    assert r2.status_code == 200
    assert r1.json()["id"] == r2.json()["id"]

    listing = await client.get("/api/v1/upstreams")
    assert listing.json()["total"] == 1


async def test_api4_unsupported_transport_pointed_message(client: AsyncClient):
    """MGMT-4: a transport other than streamable-http is a 422 naming the field and the value."""
    body = {"name": "seo", "url": "http://seo:8000/mcp", "transport": "stdio"}
    resp = await client.put("/api/v1/upstreams/seo", json=body)
    assert resp.status_code == 422
    assert "transport must be 'streamable-http'" in resp.text
    assert (await client.get("/api/v1/upstreams")).json()["total"] == 0


async def test_server_secret_headers_write_only(client: AsyncClient):
    """UPS-3: header values never leave the API."""
    body = {"name": "s1", "url": "http://s1/mcp", "static_headers": {"authorization": "secret1"}}
    resp = await client.put("/api/v1/upstreams/s1", json=body)
    assert resp.status_code == 200
    assert "secret1" not in resp.text
    assert resp.json()["static_header_names"] == ["authorization"]


async def test_server_name_rules(client: AsyncClient):
    """ARC-19: bad slug and double-underscore rejected."""
    bad = await client.put("/api/v1/upstreams/a.b", json={"name": "a.b", "url": "http://x/mcp"})
    assert bad.status_code == 422
    dbl = await client.put("/api/v1/upstreams/a__b", json={"name": "a__b", "url": "http://x/mcp"})
    assert dbl.status_code == 422


async def test_server_rename_guard(client: AsyncClient):
    """UPS-5: rename rejected while a bundle member, unless force."""
    await client.put("/api/v1/upstreams/s1", json={"name": "s1", "url": "http://x/mcp"})
    await client.put("/api/v1/bundles/b1", json={"name": "b1"})
    await client.put("/api/v1/bundles/b1/upstreams/s1", json={"enabled": True})

    denied = await client.post("/api/v1/upstreams/s1:rename", params={"new_name": "s2"})
    assert denied.status_code == 409
    forced = await client.post(
        "/api/v1/upstreams/s1:rename", params={"new_name": "s2", "force": "true"}
    )
    assert forced.status_code == 200
    assert forced.json()["name"] == "s2"


async def test_endpoint_validation_matrix(client: AsyncClient):
    """EP-1 reserved names, EP-3 none-alone rule, EP-15 matrix."""
    await client.put("/api/v1/bundles/b1", json={"name": "b1"})

    reserved = await client.put(
        "/api/v1/endpoints/oauth", json={"name": "oauth", "bundle_name": "b1"}
    )
    assert reserved.status_code == 422

    none_mixed = await client.put(
        "/api/v1/endpoints/e1",
        json={"name": "e1", "bundle_name": "b1", "auth_modes": ["none", "api_key"]},
    )
    assert none_mixed.status_code == 422

    none_unflagged = await client.put(
        "/api/v1/endpoints/e1", json={"name": "e1", "bundle_name": "b1", "auth_modes": ["none"]}
    )
    assert none_unflagged.status_code == 422

    oauth_only_bad = await client.put(
        "/api/v1/endpoints/e1",
        json={
            "name": "e1",
            "bundle_name": "b1",
            "profile": "oauth_only",
            "auth_modes": ["api_key"],
        },
    )
    assert oauth_only_bad.status_code == 422

    ok = await client.put(
        "/api/v1/endpoints/e1",
        json={"name": "e1", "bundle_name": "b1", "profile": "oauth_only", "auth_modes": ["oauth"]},
    )
    assert ok.status_code == 200


@pytest.mark.parametrize("former", ["claude", "chatgpt"])
async def test_ep23_former_profile_identifier_rejected(client: AsyncClient, former: str):
    """EP-23: a former profile identifier is a validation error listing the accepted values."""
    await client.put("/api/v1/bundles/b1", json={"name": "b1"})
    resp = await client.put(
        "/api/v1/endpoints/e1",
        json={"name": "e1", "bundle_name": "b1", "profile": former, "auth_modes": ["oauth"]},
    )
    assert resp.status_code == 422
    for accepted in ("default", "oauth_only", "write_as_read"):
        assert accepted in resp.text


async def test_ep14_ep23_profile_listing(client: AsyncClient):
    """EP-14/EP-23: the listing names each profile for its effect; only write_as_read warns."""
    listing = (await client.get("/api/v1/endpoints/profiles")).json()
    assert [p["name"] for p in listing] == ["default", "oauth_only", "write_as_read"]
    assert all(p["description"] for p in listing)
    warned = [p["name"] for p in listing if p.get("warning")]
    assert warned == ["write_as_read"]


async def test_endpoint_rename_needs_force(client: AsyncClient):
    """EP-8."""
    await client.put("/api/v1/bundles/b1", json={"name": "b1"})
    await client.put("/api/v1/endpoints/e1", json={"name": "e1", "bundle_name": "b1"})

    denied = await client.post("/api/v1/endpoints/e1:rename", params={"new_name": "e2"})
    assert denied.status_code == 409
    forced = await client.post(
        "/api/v1/endpoints/e1:rename", params={"new_name": "e2", "force": "true"}
    )
    assert forced.status_code == 200


async def test_delete_idempotent(client: AsyncClient):
    """MGMT-6: deleting a missing resource is 204."""
    resp = await client.delete("/api/v1/upstreams/ghost")
    assert resp.status_code == 204


async def test_api_key_lifecycle(client: AsyncClient):
    """AUTH-22 one-time value, AUTH-25 deactivation."""
    created = await client.post("/api/v1/api-keys", json={"name": "k1", "kind": "endpoint"})
    assert created.status_code == 201
    payload = created.json()
    assert payload["key"].startswith("bmcp_sk_")

    listing = await client.get("/api/v1/api-keys")
    items = listing.json()["items"]
    assert all("key" not in item for item in items)  # value never listed again

    target = next(i for i in items if i["name"] == "k1")
    deact = await client.post(f"/api/v1/api-keys/{target['id']}:deactivate")
    assert deact.status_code == 200
    assert deact.json()["is_active"] is False


async def test_pagination_limits(client: AsyncClient):
    """MGMT-5: limit capped at 500, default 50."""
    resp = await client.get("/api/v1/upstreams", params={"limit": 9999})
    assert resp.status_code == 422


async def test_pagination_bounds(client: AsyncClient):
    """MGMT-5: offset and limit are validated; the envelope echoes them."""
    ok = await client.get("/api/v1/upstreams", params={"offset": 0, "limit": 500})
    assert ok.status_code == 200 and ok.json()["limit"] == 500
    for params in ({"limit": 0}, {"limit": 501}, {"offset": -1}, {"limit": "many"}):
        assert (await client.get("/api/v1/upstreams", params=params)).status_code == 422, params
    default = (await client.get("/api/v1/upstreams")).json()
    assert default["offset"] == 0 and default["limit"] == 50


async def test_ep24_allowed_origins_default_by_auth_mode(client: AsyncClient):
    """EP-24: an omitted list is [] for an open endpoint and ['*'] for one needing a credential."""
    await client.put("/api/v1/bundles/b1", json={"name": "b1"})
    keyed = await client.put("/api/v1/endpoints/k", json={"name": "k", "bundle_name": "b1"})
    assert keyed.json()["allowed_origins"] == ["*"]
    open_ = await client.put(
        "/api/v1/endpoints/o",
        json={
            "name": "o",
            "bundle_name": "b1",
            "auth_modes": ["none"],
            "allow_unauthenticated": True,
        },
    )
    assert open_.json()["allowed_origins"] == []


async def test_ep24_allowed_origins_round_trip_normalised(client: AsyncClient):
    """EP-24: a listed origin is stored normalised, and an upsert without it resets the default."""
    await client.put("/api/v1/bundles/b1", json={"name": "b1"})
    body = {"name": "e", "bundle_name": "b1", "allowed_origins": ["https://App.example/"]}
    saved = await client.put("/api/v1/endpoints/e", json=body)
    assert saved.status_code == 200
    assert saved.json()["allowed_origins"] == ["https://app.example"]
    assert (await client.get("/api/v1/endpoints/e")).json()["allowed_origins"] == [
        "https://app.example"
    ]
    replaced = await client.put("/api/v1/endpoints/e", json={"name": "e", "bundle_name": "b1"})
    assert replaced.json()["allowed_origins"] == ["*"]


@pytest.mark.parametrize(
    ("origins", "named"),
    [
        (["https://app.example/path"], "https://app.example/path"),
        (["app.example"], "app.example"),
        (["*", "https://app.example"], "'*'"),
    ],
    ids=["path", "no-scheme", "wildcard-mixed"],
)
async def test_ep24_invalid_allowed_origins_are_rejected(client: AsyncClient, origins, named):
    """EP-24: each invalid entry answers 422 naming it."""
    await client.put("/api/v1/bundles/b1", json={"name": "b1"})
    resp = await client.put(
        "/api/v1/endpoints/e",
        json={"name": "e", "bundle_name": "b1", "allowed_origins": origins},
    )
    assert resp.status_code == 422
    assert named in resp.text


GATEWAY = "http://localhost:8000"  # the hermetic app's public URL


async def test_bnd5_own_endpoint_answers_409_and_stores_no_membership(client: AsyncClient):
    """BND-5: adding the gateway itself to a bundle answers 409 naming the self-reference."""
    await client.put("/api/v1/bundles/b1", json={"name": "b1"})
    registered = await client.put(
        "/api/v1/upstreams/loop", json={"name": "loop", "url": f"{GATEWAY}/loop-ep/mcp"}
    )
    assert registered.status_code == 200  # a non-member may point anywhere
    resp = await client.put("/api/v1/bundles/b1/upstreams/loop", json={"enabled": True})
    assert resp.status_code == 409
    assert "own MCP endpoints" in resp.text
    assert (await client.get("/api/v1/bundles/b1/upstreams")).json() == []


async def test_bnd5_changing_a_members_url_to_the_gateway_answers_409(client: AsyncClient):
    """BND-5: the URL change is refused and the stored URL is unchanged."""
    await client.put("/api/v1/bundles/b1", json={"name": "b1"})
    await client.put("/api/v1/upstreams/weather", json={"name": "weather", "url": "http://w/mcp"})
    await client.put("/api/v1/bundles/b1/upstreams/weather", json={"enabled": True})
    resp = await client.put(
        "/api/v1/upstreams/weather", json={"name": "weather", "url": f"{GATEWAY}/b1-ep/mcp"}
    )
    assert resp.status_code == 409
    assert (await client.get("/api/v1/upstreams/weather")).json()["url"] == "http://w/mcp"


async def test_auth26_a_deactivated_key_is_refused_on_the_next_request(client: AsyncClient):
    """AUTH-26: no validation cache: deactivating a key stops it on the very next request."""
    created = await client.post("/api/v1/api-keys", json={"name": "ops", "kind": "service"})
    key, key_id = created.json()["key"], created.json()["id"]
    as_key = {"Authorization": f"Bearer {key}"}
    assert (await client.get("/api/v1/upstreams", headers=as_key)).status_code == 200
    await client.post(f"/api/v1/api-keys/{key_id}:deactivate")
    assert (await client.get("/api/v1/upstreams", headers=as_key)).status_code == 401
