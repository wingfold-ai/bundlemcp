"""The Controller base: routes bind in the order written, and an override cannot lose its route."""

import pytest
from bundlemcp.api.http.controller import Controller
from bundlemcp.api.http.route import route
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


class Things(Controller):
    prefix = "/things"

    @route.get("/special")
    async def special(self) -> dict:
        return {"which": "literal"}

    @route.get("/{name}")
    async def one(self, name: str) -> dict:
        return {"which": name}


class MoreThings(Things):
    @route.get("/special")
    async def special(self) -> dict:
        return {"which": "overridden"}

    @route.get("/extra/thing")
    async def extra(self) -> dict:
        return {"which": "extra"}


def test_routes_keep_source_order_across_the_hierarchy():
    """A literal path declared before its parameterised sibling stays ahead of it."""
    assert [path for _, spec in Things._routes() for path in [spec.path]] == ["/special", "/{name}"]
    assert [spec.path for _, spec in MoreThings._routes()] == [
        "/special",
        "/{name}",
        "/extra/thing",
    ]


async def test_overriding_a_route_serves_the_override():
    app = FastAPI()
    MoreThings().mount(app)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as http:
        assert (await http.get("/things/special")).json() == {"which": "overridden"}
        assert (await http.get("/things/other")).json() == {"which": "other"}
        assert (await http.get("/things/extra/thing")).json() == {"which": "extra"}


def test_undecorated_override_is_refused():
    """Forgetting @route on an override would silently drop the route, so it is an error."""

    class Broken(Things):
        async def special(self) -> dict:  # no @route
            return {}

    with pytest.raises(TypeError, match="Broken.special overrides a route"):
        Broken()
