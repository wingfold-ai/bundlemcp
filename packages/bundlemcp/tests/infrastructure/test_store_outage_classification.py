"""Only a failure to reach the database counts as a store outage (SES-14)."""

import pytest
from bundlemcp.application.contracts.persistence.store_unavailable import StoreUnavailable
from bundlemcp.infrastructure.postgres.engine import session_factory
from bundlemcp.infrastructure.postgres.sqlalchemy_unit_of_work import (
    SqlAlchemyUnitOfWorkFactory,
    is_store_outage,
)
from sqlalchemy.exc import IntegrityError, OperationalError


def _raised(exc: Exception) -> Exception:
    try:
        raise exc
    except Exception as caught:
        return caught


def test_ses14_connection_failures_are_outages():
    assert is_store_outage(OperationalError("SELECT 1", {}, ConnectionRefusedError()))


def test_ses14_a_query_that_ran_and_failed_is_not_an_outage():
    assert not is_store_outage(IntegrityError("INSERT", {}, ValueError("duplicate")))


def test_ses14_a_network_error_from_outside_the_driver_is_not_an_outage():
    """An upstream probe's refused connection inside a unit of work is not the database's."""
    assert not is_store_outage(_raised(ConnectionRefusedError("upstream refused")))


async def test_ses14_the_unit_of_work_raises_store_unavailable(engine, redis):
    units = SqlAlchemyUnitOfWorkFactory(session_factory(engine), redis)
    with pytest.raises(StoreUnavailable):
        async with units.open():
            raise OperationalError("SELECT 1", {}, ConnectionRefusedError())
    with pytest.raises(ValueError):
        async with units.open():
            raise ValueError("a service's own failure passes through")
