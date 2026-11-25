"""Looking up a key by kind works when several keys of that kind are stored."""

import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager

import pytest
from bundlemcp.domain.access.api_key import ApiKey
from bundlemcp.domain.access.api_key_kind import ApiKeyKind
from bundlemcp.infrastructure.memory.in_memory_unit_of_work import InMemoryUnitOfWorkFactory
from bundlemcp.infrastructure.postgres.engine import session_factory
from bundlemcp.infrastructure.postgres.sqlalchemy_unit_of_work import SqlAlchemyUnitOfWorkFactory

Opener = Callable[[], AbstractAsyncContextManager]


def _key(name: str, kind: ApiKeyKind) -> ApiKey:
    return ApiKey(id=uuid.uuid4(), name=name, key_hash=f"h-{name}", key_prefix="p", kind=kind)


@pytest.fixture(params=["memory", "sqlite"])
async def opener(request, engine, redis) -> AsyncIterator[Opener]:
    """A unit-of-work opener of either kind, seeded with two service keys and one endpoint key."""
    if request.param == "memory":
        units = InMemoryUnitOfWorkFactory()
    else:
        units = SqlAlchemyUnitOfWorkFactory(session_factory(engine), redis)
    async with units.open() as uow:
        uow.api_keys.add(_key("initial-service-key", ApiKeyKind.SERVICE))
        uow.api_keys.add(_key("sync", ApiKeyKind.SERVICE))
        uow.api_keys.add(_key("claude", ApiKeyKind.ENDPOINT))
        await uow.commit()
    yield units.open


async def test_any_of_kind_with_several_keys_of_that_kind(opener):
    async with opener() as uow:
        found = await uow.api_keys.any_of_kind(ApiKeyKind.SERVICE)
    assert found is not None
    assert found.kind is ApiKeyKind.SERVICE
    assert found.name in {"initial-service-key", "sync"}


async def test_any_of_kind_with_none_of_that_kind(engine, redis):
    units = SqlAlchemyUnitOfWorkFactory(session_factory(engine), redis)
    async with units.open() as uow:
        uow.api_keys.add(_key("claude", ApiKeyKind.ENDPOINT))
        await uow.commit()
    async with units.open() as uow:
        assert await uow.api_keys.any_of_kind(ApiKeyKind.SERVICE) is None
