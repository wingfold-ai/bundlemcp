"""Providers for the collaborators the composition root publishes.

Each ``get_*`` reads one field off the app's container; the ``*Provider``
alias injects it into a route signature. ``get_unit_of_work`` is the exception
that opens a request-scoped unit of work rather than handing out a shared object.
"""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request

from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWork, UnitOfWorkFactory
from bundlemcp.application.contracts.readiness_probe import ReadinessProbe
from bundlemcp.application.settings.settings import Settings


async def get_unit_of_work(request: Request) -> AsyncIterator[UnitOfWork]:
    factory: UnitOfWorkFactory = request.app.state.container.unit_of_work_factory
    async with factory.open() as uow:
        yield uow


def get_readiness(request: Request) -> ReadinessProbe:
    return request.app.state.container.readiness


def get_app_settings(request: Request) -> Settings:
    return request.app.state.container.settings


UnitOfWorkProvider = Annotated[UnitOfWork, Depends(get_unit_of_work)]
ReadinessProvider = Annotated[ReadinessProbe, Depends(get_readiness)]
SettingsProvider = Annotated[Settings, Depends(get_app_settings)]
