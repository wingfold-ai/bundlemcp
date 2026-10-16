"""Bundle rename on the in-memory fakes (BND-10)."""

import pytest
from bundlemcp.application.errors import ConflictError
from bundlemcp.application.management.bundle_service import BundleService
from bundlemcp.application.schemas import BundleUpsert
from bundlemcp.infrastructure.memory.in_memory_unit_of_work import InMemoryUnitOfWork


async def test_bnd10_rename_announces_both_names():
    """BND-10: a rename publishes a bundle change under the old and the new name, so streams
    keyed on either hear that the tool list changed."""
    uow = InMemoryUnitOfWork()
    bundles = BundleService(uow, public_base="http://gw")
    created = await bundles.upsert(BundleUpsert(name="b1"))
    uow.published.clear()

    renamed = await bundles.rename("b1", "b2", force=True)

    assert renamed.id == created.id
    assert sorted(e.key for e in uow.published if e.entity_type == "bundle") == ["b1", "b2"]


async def test_bnd10_refused_rename_publishes_nothing():
    """BND-10: a rename refused for want of force changes and announces nothing."""
    uow = InMemoryUnitOfWork()
    bundles = BundleService(uow, public_base="http://gw")
    await bundles.upsert(BundleUpsert(name="b1"))
    uow.published.clear()

    with pytest.raises(ConflictError, match="BND-10"):
        await bundles.rename("b1", "b2", force=False)

    assert uow.published == []
    assert (await bundles.get("b1")).name == "b1"
