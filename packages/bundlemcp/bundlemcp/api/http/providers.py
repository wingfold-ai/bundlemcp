"""Providers for the collaborators the composition root publishes.

Each ``get_*`` reads one field off the app's container; the ``*Provider``
alias injects it into a route signature. ``get_unit_of_work`` is the exception
that opens a request-scoped unit of work rather than handing out a shared object.
"""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, FastAPI, Request

from bundlemcp.api.http.client_ip import client_ip
from bundlemcp.application.contracts.observability.metrics_exposition import MetricsExposition
from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWork, UnitOfWorkFactory
from bundlemcp.application.contracts.readiness_probe import ReadinessProbe
from bundlemcp.application.serving.replica_drain import ReplicaDrain
from bundlemcp.application.settings.settings import Settings
from bundlemcp.domain.config.runtime_settings import RuntimeSettings


async def get_unit_of_work(request: Request) -> AsyncIterator[UnitOfWork]:
    factory: UnitOfWorkFactory = request.app.state.container.unit_of_work_factory
    async with factory.open() as uow:
        yield uow


def get_readiness(request: Request) -> ReadinessProbe:
    return request.app.state.container.readiness


def get_drain(request: Request) -> ReplicaDrain:
    return request.app.state.container.drain


def get_metrics_exposition(request: Request) -> MetricsExposition:
    return request.app.state.container.metrics_exposition


def get_app_settings(request: Request) -> Settings:
    return request.app.state.container.settings


def get_client_ip(request: Request) -> str:
    return client_ip(request, request.app.state.container.settings)


def current_request_limit(app: FastAPI) -> int:
    """The request body limit in bytes, from the config snapshot; never does I/O.

    Before the composition root has published its container (a request racing
    startup) it is the registry default.
    """
    container = getattr(app.state, "container", None)
    if container is None:
        return RuntimeSettings().max_request_bytes
    return container.runtime_config.snapshot.max_request_bytes


UnitOfWorkProvider = Annotated[UnitOfWork, Depends(get_unit_of_work)]
ReadinessProvider = Annotated[ReadinessProbe, Depends(get_readiness)]
DrainProvider = Annotated[ReplicaDrain, Depends(get_drain)]
SettingsProvider = Annotated[Settings, Depends(get_app_settings)]
ClientIpProvider = Annotated[str, Depends(get_client_ip)]
MetricsExpositionProvider = Annotated[MetricsExposition, Depends(get_metrics_exposition)]
