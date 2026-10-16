"""Liveness and readiness probes."""

from fastapi.responses import JSONResponse

from bundlemcp.api.http.controller import Controller
from bundlemcp.api.http.providers import DrainProvider, ReadinessProvider
from bundlemcp.api.http.route import route


class HealthController(Controller):
    include_in_schema = False

    @route.get("/healthz")
    async def healthz(self) -> dict[str, str]:
        return {"status": "ok"}

    @route.get("/readyz")
    async def readyz(self, readiness: ReadinessProvider, drain: DrainProvider) -> JSONResponse:
        """Ready means both stores answer, the schema is current and the replica is not stopping.

        Not ready is 503 with the failing checks named; nothing here answers 500.
        """
        if drain.draining:
            return JSONResponse(status_code=503, content={"status": "draining"})
        report = await readiness.check()
        if report.ready:
            return JSONResponse(content={"status": "ready"})
        return JSONResponse(
            status_code=503,
            content={
                "status": "not ready",
                "failing": report.failing,
                "checks": report.model_dump(exclude_none=True),
            },
        )
