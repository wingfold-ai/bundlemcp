"""Bundle-owned prompts and resources (spec 17) through the management API and its storage."""

import pytest
from httpx import AsyncClient

PROMPT = {
    "name": "plot",
    "title": "Plot a series",
    "arguments": [{"name": "series", "required": True, "values": ["revenue", "costs"]}],
    "messages": [
        {"role": "user", "text": "Plot {{series}}."},
        {"role": "user", "resource": "guides/style"},
    ],
}
RESOURCE = {"name": "guides/style", "title": "House style", "content": "# Style\n\nUse blue."}


@pytest.fixture
async def client(service_client: AsyncClient) -> AsyncClient:
    resp = await service_client.put("/api/v1/bundles/charts", json={"name": "charts"})
    assert resp.status_code == 200
    return service_client


async def test_resource_round_trip_with_folder_name(client):
    """BPR-14, BPR-6: a name with '/' folders is addressed through the path as written."""
    put = await client.put("/api/v1/bundles/charts/resources/guides/style", json=RESOURCE)
    assert put.status_code == 200, put.text
    body = put.json()
    assert body["uri"] == "bundle://resources/guides/style"
    assert body["mime_type"] == "text/markdown"
    assert body["size_bytes"] == len(RESOURCE["content"].encode())

    got = await client.get("/api/v1/bundles/charts/resources/guides/style")
    assert got.json()["content"] == RESOURCE["content"]
    listing = await client.get("/api/v1/bundles/charts/resources")
    assert [r["name"] for r in listing.json()["items"]] == ["guides/style"]

    deleted = await client.delete("/api/v1/bundles/charts/resources/guides/style")
    assert deleted.status_code == 204
    assert (await client.get("/api/v1/bundles/charts/resources/guides/style")).status_code == 404


async def test_prompt_round_trip(client):
    """BPR-14: GET, idempotent PUT, paginated list and DELETE under the bundle."""
    await client.put("/api/v1/bundles/charts/resources/guides/style", json=RESOURCE)
    first = await client.put("/api/v1/bundles/charts/prompts/plot", json=PROMPT)
    second = await client.put("/api/v1/bundles/charts/prompts/plot", json=PROMPT)
    assert first.status_code == second.status_code == 200, first.text
    assert first.json()["created_at"] == second.json()["created_at"]
    assert second.json()["messages"][1] == {
        "role": "user",
        "text": None,
        "resource": "guides/style",
    }

    listing = (await client.get("/api/v1/bundles/charts/prompts")).json()
    assert listing["total"] == 1 and listing["items"][0]["arguments"][0]["values"] == [
        "revenue",
        "costs",
    ]
    assert (await client.delete("/api/v1/bundles/charts/prompts/plot")).status_code == 204
    assert (await client.get("/api/v1/bundles/charts/prompts/plot")).status_code == 404


@pytest.mark.parametrize(
    ("path", "body", "fragment"),
    [
        ("prompts/other", PROMPT, "must match"),
        ("prompts/a__b", {**PROMPT, "name": "a__b"}, "__"),
        ("prompts/plot", PROMPT, "guides/style"),  # BPR-3: resource not there yet
        ("prompts/plot", {**PROMPT, "messages": []}, "messages"),
        ("resources/x", {"name": "x", "content": "", "mime_type": "image/png"}, "mime_type"),
    ],
)
async def test_invalid_writes_are_rejected(client, path, body, fragment):
    """BPR-2, BPR-3, BPR-6: rejected with 422 and a message that says why."""
    resp = await client.put(f"/api/v1/bundles/charts/{path}", json=body)
    assert resp.status_code == 422
    assert fragment in resp.text


async def test_unknown_bundle_is_404(client):
    resp = await client.put("/api/v1/bundles/nope/resources/x", json={"name": "x", "content": ""})
    assert resp.status_code == 404


async def test_embedded_resource_delete_conflicts(client):
    await client.put("/api/v1/bundles/charts/resources/guides/style", json=RESOURCE)
    await client.put("/api/v1/bundles/charts/prompts/plot", json=PROMPT)
    resp = await client.delete("/api/v1/bundles/charts/resources/guides/style")
    assert resp.status_code == 409 and "plot" in resp.text


async def test_content_goes_with_its_bundle(client):
    """DOM-2: deleting the bundle removes its prompts and resources."""
    await client.put("/api/v1/bundles/charts/resources/guides/style", json=RESOURCE)
    await client.put("/api/v1/bundles/charts/prompts/plot", json=PROMPT)
    assert (await client.delete("/api/v1/bundles/charts")).status_code == 204
    await client.put("/api/v1/bundles/charts", json={"name": "charts"})
    assert (await client.get("/api/v1/bundles/charts/prompts")).json()["total"] == 0
    assert (await client.get("/api/v1/bundles/charts/resources")).json()["total"] == 0


async def test_same_name_in_two_bundles(client):
    """BPR-1, BPR-6: the natural key is (bundle, name)."""
    await client.put("/api/v1/bundles/other", json={"name": "other"})
    for bundle in ("charts", "other"):
        resp = await client.put(f"/api/v1/bundles/{bundle}/resources/guides/style", json=RESOURCE)
        assert resp.status_code == 200
