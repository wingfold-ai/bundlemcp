"""Bundle-owned prompts and resources: the management use cases on the fakes."""

import pytest
from bundlemcp.application.bootstrap.bootstrap_document import BootstrapDocument
from bundlemcp.application.bootstrap.bootstrap_runner import BootstrapRunner
from bundlemcp.application.errors import ConflictError, InvalidInputError, NotFoundError
from bundlemcp.application.management.bundle_prompt_service import BundlePromptService
from bundlemcp.application.management.bundle_resource_service import BundleResourceService
from bundlemcp.application.management.bundle_service import BundleService
from bundlemcp.application.schemas import BundlePromptUpsert, BundleResourceUpsert, BundleUpsert
from bundlemcp.application.serving.bundle_content_reader import BundleContentReader
from bundlemcp.domain.bundles.bundle_content_limits import BundleContentLimits
from bundlemcp.infrastructure.memory.in_memory_unit_of_work import (
    InMemoryUnitOfWork,
    InMemoryUnitOfWorkFactory,
)
from bundlemcp.infrastructure.memory.no_upstream_connections import NoUpstreamConnections
from bundlemcp.infrastructure.memory.noop_tool_discovery import NoopToolDiscovery


@pytest.fixture
async def uow() -> InMemoryUnitOfWork:
    uow = InMemoryUnitOfWork()
    await BundleService(uow).upsert(BundleUpsert(name="charts"))
    uow.published.clear()
    return uow


def _prompt(name="plot", text="Plot {{series}}.", **extra) -> BundlePromptUpsert:
    return BundlePromptUpsert.model_validate(
        {
            "name": name,
            "arguments": [{"name": "series", "required": True}],
            "messages": [{"role": "user", "text": text}],
            **extra,
        }
    )


def _resource(name="guides/style", content="# Style", **extra) -> BundleResourceUpsert:
    return BundleResourceUpsert(name=name, content=content, **extra)


async def test_prompt_upsert_is_idempotent_and_announces_a_prompt_change(uow):
    """BND-31, BND-28: upsert by name; each write is announced under the bundle's name."""
    prompts = BundlePromptService(uow)
    first = await prompts.upsert("charts", _prompt())
    second = await prompts.upsert("charts", _prompt(text="Chart {{series}}."))
    assert second.created_at == first.created_at
    assert second.messages[0].text == "Chart {{series}}."
    assert [(e.entity_type, e.key, e.action) for e in uow.published] == [
        ("bundle_prompt", "charts", "created"),
        ("bundle_prompt", "charts", "updated"),
    ]
    assert len(uow.bundle_prompts.rows) == 1


async def test_prompt_with_undeclared_placeholder_is_rejected(uow):
    """BND-20"""
    with pytest.raises(InvalidInputError, match="kind"):
        await BundlePromptService(uow).upsert("charts", _prompt(text="{{series}} {{kind}}"))
    assert uow.published == []


async def test_prompt_may_embed_only_an_existing_resource(uow):
    """BND-20: the embedded resource must already belong to the bundle."""
    prompts = BundlePromptService(uow)
    embedding = _prompt(messages=[{"role": "user", "resource": "guides/style"}])
    with pytest.raises(InvalidInputError, match="guides/style"):
        await prompts.upsert("charts", embedding)
    await BundleResourceService(uow).upsert("charts", _resource())
    stored = await prompts.upsert("charts", embedding)
    assert stored.messages[0].resource == "guides/style"


async def test_embedded_resource_cannot_be_deleted(uow):
    """A resource a prompt embeds is kept, so no prompt points at nothing."""
    resources = BundleResourceService(uow)
    await resources.upsert("charts", _resource())
    await BundlePromptService(uow).upsert(
        "charts", _prompt(messages=[{"role": "user", "resource": "guides/style"}])
    )
    with pytest.raises(ConflictError, match="plot"):
        await resources.delete("charts", "guides/style")
    await BundlePromptService(uow).delete("charts", "plot")
    await resources.delete("charts", "guides/style")
    assert uow.bundle_resources.rows == []


async def test_prompt_count_limit_counts_only_new_names(uow):
    """BND-33: replacing an existing prompt never trips the count limit."""
    prompts = BundlePromptService(uow, BundleContentLimits(max_prompts=1))
    await prompts.upsert("charts", _prompt())
    await prompts.upsert("charts", _prompt(text="again {{series}}"))
    with pytest.raises(InvalidInputError, match="at most 1 prompts"):
        await prompts.upsert("charts", _prompt(name="other"))


async def test_bundle_resource_total_excludes_the_entry_being_replaced(uow):
    """BND-33: the 4 MiB total counts the new content, not the old and the new together."""
    resources = BundleResourceService(uow, BundleContentLimits(max_bundle_resource_bytes=10))
    await resources.upsert("charts", _resource(name="a", content="x" * 6))
    await resources.upsert("charts", _resource(name="a", content="y" * 8))
    with pytest.raises(InvalidInputError, match="resources would total 11 bytes"):
        await resources.upsert("charts", _resource(name="b", content="zzz"))


async def test_resource_read_carries_uri_and_size(uow):
    """BND-23, BND-24"""
    read = await BundleResourceService(uow).upsert(
        "charts", _resource(content="ü", mime_type="text/plain")
    )
    assert read.uri == "bundle://resources/guides/style"
    assert read.size_bytes == 2
    assert read.mime_type == "text/plain"


async def test_unknown_bundle_and_entry_are_not_found(uow):
    with pytest.raises(NotFoundError, match="bundle"):
        await BundlePromptService(uow).upsert("nope", _prompt())
    with pytest.raises(NotFoundError, match="prompt"):
        await BundlePromptService(uow).get("charts", "nope")
    with pytest.raises(NotFoundError, match="resource"):
        await BundleResourceService(uow).get("charts", "nope")


async def test_delete_is_idempotent(uow):
    await BundlePromptService(uow).delete("charts", "never-existed")
    await BundleResourceService(uow).delete("charts", "never-existed")
    assert uow.published == []


async def test_list_pages_in_name_order(uow):
    """BND-31: paginated collection, sorted by name."""
    prompts = BundlePromptService(uow)
    for name in ("c", "a", "b"):
        await prompts.upsert("charts", _prompt(name=name))
    page = await prompts.list("charts", offset=1, limit=1)
    assert page.total == 3 and [p.name for p in page.items] == ["b"]


async def test_catalogue_lists_title_and_description_only(uow):
    """BND-36"""
    await BundlePromptService(uow).upsert("charts", _prompt(title="Plot", description="A chart"))
    await BundleResourceService(uow).upsert("charts", _resource(title="Style guide"))
    bundle = await uow.bundles.by_name("charts")
    prompts = await BundlePromptService(uow).catalogue(bundle.id)
    resources = await BundleResourceService(uow).catalogue(bundle.id)
    assert [p.model_dump() for p in prompts] == [
        {"name": "plot", "title": "Plot", "description": "A chart"}
    ]
    assert [r.model_dump() for r in resources] == [
        {"name": "guides/style", "title": "Style guide", "description": None}
    ]


async def test_reader_renders_with_embedded_resources(uow):
    """BND-20, BND-25: the reader substitutes arguments and fetches what a message embeds."""
    await BundleResourceService(uow).upsert("charts", _resource())
    await BundlePromptService(uow).upsert(
        "charts",
        _prompt(
            messages=[
                {"role": "user", "text": "Plot {{series}}."},
                {"role": "user", "resource": "guides/style"},
            ]
        ),
    )
    bundle = await uow.bundles.by_name("charts")
    reader = BundleContentReader(InMemoryUnitOfWorkFactory(uow))
    rendered = await reader.render_prompt(bundle.id, "plot", {"series": "revenue"})
    assert rendered.messages[0].text == "Plot revenue."
    assert rendered.resources["guides/style"].content == "# Style"
    assert await reader.render_prompt(bundle.id, "nope", {}) is None


async def test_bootstrap_applies_resources_before_the_prompts_that_embed_them(uow):
    """BND-32: a bundle entry carries its prompts and resources, upserted by name."""
    document = BootstrapDocument.model_validate(
        {
            "bundles": [
                {
                    "name": "charts",
                    "prompts": [
                        {
                            "name": "plot",
                            "messages": [{"role": "user", "resource": "guides/style"}],
                        }
                    ],
                    "resources": [{"name": "guides/style", "content": "# Style"}],
                }
            ]
        }
    )
    runner = BootstrapRunner(
        InMemoryUnitOfWorkFactory(uow),
        NoopToolDiscovery(),
        cipher=None,
        connections=NoUpstreamConnections(),
    )
    await runner.apply(document)
    await runner.apply(document)  # applying twice changes nothing
    assert [p.name for p in uow.bundle_prompts.rows] == ["plot"]
    assert [r.name for r in uow.bundle_resources.rows] == ["guides/style"]


def test_bootstrap_bundle_entry_still_rejects_unknown_keys():
    """MGMT-15: the new keys are declared; a misspelt one still fails."""
    with pytest.raises(ValueError, match="prompt"):
        BootstrapDocument.model_validate({"bundles": [{"name": "b", "prompt": []}]})
