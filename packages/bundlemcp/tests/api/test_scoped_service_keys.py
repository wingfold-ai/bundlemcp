"""Scoped service keys (AUTH-40, MGMT-23, AUTH-5, ADR-0066)."""

import uuid
from dataclasses import dataclass

import pytest
from bundlemcp.api.http.controller import ACCESS_EXTENSION
from bundlemcp.api.http.route import route
from bundlemcp.api.management.controllers.management_controller import ManagementController
from bundlemcp.domain.access.api_key_kind import ApiKeyKind
from bundlemcp.domain.access.api_key_scope import FULL, ApiKeyScope
from fastapi.routing import APIRoute

from tests.api.test_gateway import _initialize_raw, _running
from tests.conftest import ENDPOINT_KEY, SERVICE_KEY, seed_api_key

ALL_SCOPES = [s.value for s in ApiKeyScope]
SERVICE = {"Authorization": f"Bearer {SERVICE_KEY}"}


@pytest.fixture
async def gw(engine, redis):
    await seed_api_key(engine, SERVICE_KEY)
    async with _running(engine, redis) as (http, app):
        yield http, app


async def _key(http, scopes: list[str], kind: str = "service", name: str | None = None) -> str:
    created = await http.post(
        "/api/v1/api-keys",
        json={"name": name or f"k-{uuid.uuid4().hex[:8]}", "kind": kind, "scopes": scopes},
        headers=SERVICE,
    )
    assert created.status_code == 201, created.text
    return created.json()["key"]


@dataclass(frozen=True)
class Served:
    """One route as the app serves it: its full path, verbs and declared access."""

    path: str
    methods: frozenset[str]
    access: str | None


def _served(routes) -> list[Served]:
    """Every route the app serves, through included routers.

    FastAPI includes routers lazily; their effective routes carry the full path and the
    route's OpenAPI extensions. This walks them the way the router does when it matches.
    """
    out: list[Served] = []
    for r in routes:
        if isinstance(r, APIRoute):
            out.append(
                Served(r.path, frozenset(r.methods), (r.openapi_extra or {}).get(ACCESS_EXTENSION))
            )
        elif hasattr(r, "effective_candidates"):
            for c in r.effective_candidates():
                if hasattr(c, "effective_candidates"):
                    out += _served([c])
                elif isinstance(c.original_route, APIRoute):
                    out.append(
                        Served(
                            c.path,
                            frozenset(c.original_route.methods),
                            (c.openapi_extra or {}).get(ACCESS_EXTENSION),
                        )
                    )
    return out


def _management_routes(app) -> list[Served]:
    return [r for r in _served(app.routes) if r.path.startswith("/api/v1") or r.path == "/metrics"]


def _access(r: Served) -> str | None:
    return r.access


def _url(path: str) -> str:
    out = path
    for param in ("{name:path}", "{key_id}", "{user_id}", "{consent_id}", "{tool_id}"):
        out = out.replace(param, str(uuid.uuid4()) if "id" in param else "x")
    for param in ("{prompt_id}", "{resource_id}"):
        out = out.replace(param, str(uuid.uuid4()))
    while "{" in out:
        start = out.index("{")
        out = out[:start] + "x" + out[out.index("}", start) + 1 :]
    return out


async def test_mgmt23_every_management_route_declares_its_access(gw):
    """MGMT-23: every /api/v1 route and /metrics names a scope or full access; none is left
    to a default."""
    _http, app = gw
    routes = _management_routes(app)
    assert len(routes) > 60
    undeclared = [f"{sorted(r.methods)} {r.path}" for r in routes if _access(r) is None]
    assert undeclared == []
    known = set(ALL_SCOPES) | {FULL}
    assert {_access(r) for r in routes} <= known
    # introspection and MCP calls are not management routes; no route asks for them
    assert {_access(r) for r in routes}.isdisjoint({"introspect", "mcp"})


def test_mgmt23_a_management_route_without_access_cannot_be_built():
    """MGMT-23: forgetting the declaration fails when the controller is built."""

    class Careless(ManagementController):
        prefix = "/careless"

        @route.get("")
        async def nothing(self) -> None:
            return None

    with pytest.raises(TypeError, match="declares no access"):
        Careless()


async def test_mgmt23_a_scoped_key_without_the_routes_access_gets_403_everywhere(gw):
    """MGMT-23: for every route, a key holding every scope but the one it needs is refused."""
    http, app = gw
    keys = {
        needed: await _key(http, [s for s in ALL_SCOPES if s != needed]) for needed in ALL_SCOPES
    }
    everything = await _key(http, ALL_SCOPES)
    for r in _management_routes(app):
        access = _access(r)
        key = everything if access == FULL else keys[access]
        for method in r.methods:
            resp = await http.request(
                method, _url(r.path), headers={"Authorization": f"Bearer {key}"}
            )
            assert resp.status_code == 403, (method, r.path, access, resp.status_code)


async def test_mgmt23_a_key_holding_the_routes_access_is_admitted(gw):
    """MGMT-23: a key with exactly the needed scope passes the check (any status but 401/403);
    a full-access route admits an unscoped service key."""
    http, app = gw
    keys = {s: await _key(http, [s]) for s in ALL_SCOPES}
    for r in _management_routes(app):
        if "stream" in r.path:
            continue  # an open stream would never answer
        if r.path.startswith("/api/v1/me/consents"):
            continue  # a person's own consents: no key of any kind, as before
        access = _access(r)
        key = SERVICE_KEY if access == FULL else keys[access]
        for method in r.methods:
            resp = await http.request(
                method, _url(r.path), headers={"Authorization": f"Bearer {key}"}
            )
            assert resp.status_code not in (401, 403), (method, r.path, access, resp.text)


async def test_auth40_read_and_write_scopes_on_bundles(gw):
    """AUTH-40: read lists bundles but cannot change one; bundles:write changes it."""
    http, _app = gw
    reader = {"Authorization": f"Bearer {await _key(http, ['read'])}"}
    writer = {"Authorization": f"Bearer {await _key(http, ['read', 'bundles:write'])}"}
    assert (await http.get("/api/v1/bundles", headers=reader)).status_code == 200
    body = {"name": "scoped"}
    assert (await http.put("/api/v1/bundles/scoped", json=body, headers=reader)).status_code == 403
    assert (await http.put("/api/v1/bundles/scoped", json=body, headers=writer)).status_code == 200
    endpoint = {"name": "scoped", "bundle_name": "scoped", "auth_modes": ["api_key"]}
    resp = await http.put("/api/v1/endpoints/scoped", json=endpoint, headers=writer)
    assert resp.status_code == 403


async def test_auth5_auth40_introspection_needs_the_introspect_scope(gw):
    """AUTH-5, AUTH-40: [introspect] introspects; [read] does not; unscoped still does."""
    http, _app = gw
    introspector = await _key(http, ["introspect"])
    reader = await _key(http, ["read"])
    ok = await http.post(
        "/oauth/introspect",
        data={"token": ENDPOINT_KEY},
        headers={"Authorization": f"Bearer {introspector}"},
    )
    assert ok.status_code == 200 and ok.json()["active"] is True
    refused = await http.post(
        "/oauth/introspect",
        data={"token": ENDPOINT_KEY},
        headers={"Authorization": f"Bearer {reader}"},
    )
    assert refused.status_code == 401
    full = await http.post("/oauth/introspect", data={"token": ENDPOINT_KEY}, headers=SERVICE)
    assert full.json()["active"] is True
    assert (
        await http.get("/api/v1/bundles", headers={"Authorization": f"Bearer {introspector}"})
    ).status_code == 403


async def test_auth40_only_the_mcp_scope_authenticates_mcp_calls(gw):
    """AUTH-40: a scoped key without mcp never calls a tool and introspects inactive."""
    http, _app = gw
    without = await _key(http, ["introspect", "read"])
    with_mcp = await _key(http, ["mcp"])
    for key, admitted in ((without, False), (with_mcp, True)):
        http.headers["Authorization"] = f"Bearer {key}"
        resp = await _initialize_raw(http)
        assert (resp.status_code == 200) is admitted, resp.text
        seen = await http.post("/oauth/introspect", data={"token": key}, headers=SERVICE)
        assert seen.json()["active"] is admitted


async def test_auth40_scopes_are_shown_and_validated(gw):
    """AUTH-40: scopes are listed; unknown scopes and scopes on endpoint keys are 422."""
    http, _app = gw
    await _key(http, ["read", "introspect"], name="listed")
    listed = (await http.get("/api/v1/api-keys", headers=SERVICE)).json()["items"]
    entry = next(k for k in listed if k["name"] == "listed")
    assert entry["scopes"] == ["introspect", "read"]
    assert all(k["scopes"] == [] for k in listed if k["name"] != "listed")
    for body in (
        {"name": "bad", "kind": "service", "scopes": ["admin"]},
        {"name": "ep", "kind": "endpoint", "scopes": ["read"]},
    ):
        assert (await http.post("/api/v1/api-keys", json=body, headers=SERVICE)).status_code == 422


async def test_auth40_keys_manage_never_grants_more_than_its_holder_has(gw):
    """AUTH-40: a scoped keys:manage caller manages only service keys within its own scopes."""
    http, _app = gw
    manager = {"Authorization": f"Bearer {await _key(http, ['keys:manage', 'read'])}"}

    async def create(body: dict) -> int:
        return (await http.post("/api/v1/api-keys", json=body, headers=manager)).status_code

    assert await create({"name": "sub", "kind": "service", "scopes": ["read"]}) == 201
    assert await create({"name": "full", "kind": "service"}) == 403
    assert await create({"name": "ep", "kind": "endpoint"}) == 403
    assert await create({"name": "wider", "kind": "service", "scopes": ["mcp"]}) == 403
    listed = (await http.get("/api/v1/api-keys", headers=SERVICE)).json()["items"]
    full_key = next(k for k in listed if k["kind"] == "service" and k["scopes"] == [])
    resp = await http.post(f"/api/v1/api-keys/{full_key['id']}:deactivate", headers=manager)
    assert resp.status_code == 403
    assert (
        await http.delete(f"/api/v1/api-keys/{full_key['id']}", headers=manager)
    ).status_code == 403
    sub = next(k for k in listed if k["name"] == "sub")
    assert (
        await http.post(f"/api/v1/api-keys/{sub['id']}:deactivate", headers=manager)
    ).status_code == 200


async def test_mgmt2_auth40_an_unscoped_service_key_keeps_every_right(gw):
    """MGMT-2, AUTH-40: keys without scopes behave exactly as before."""
    http, _app = gw
    assert (await http.get("/api/v1/users", headers=SERVICE)).status_code == 200
    assert (await http.get("/api/v1/me", headers=SERVICE)).json()["kind"] == "service"
    assert (await http.get("/metrics", headers=SERVICE)).status_code == 200
    assert ApiKeyKind.SERVICE.value == "service"
