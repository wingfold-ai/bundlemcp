"""Liveness and readiness probes."""

from bundlemcp.api.http.controller import Controller
from bundlemcp.api.http.providers import ReadinessProvider
from bundlemcp.api.http.route import route


class HealthController(Controller):
    include_in_schema = False

    @route.get("/healthz")
    async def healthz(self) -> dict[str, str]:
        return {"status": "ok"}

    @route.get("/readyz")
    async def readyz(self, readiness: ReadinessProvider) -> dict[str, str]:
        """Ready means both Postgres and the live store are reachable."""
        await readiness.check()
        return {"status": "ready"}
