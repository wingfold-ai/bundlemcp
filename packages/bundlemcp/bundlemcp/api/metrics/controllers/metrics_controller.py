"""This replica's metrics for a Prometheus scrape."""

from fastapi import Response

from bundlemcp.api.http.providers import MetricsExpositionProvider
from bundlemcp.api.http.route import route
from bundlemcp.api.management.controllers.management_controller import ManagementController


class MetricsController(ManagementController):
    """``/metrics``, behind the management API's credentials: a service key or an admin session.

    Metrics name endpoints and servers and show traffic volume, so they are not
    public. Each replica answers with its own values; a scrape job lists every
    replica.
    """

    include_in_schema = False

    @route.get("/metrics")
    async def metrics(self, exposition: MetricsExpositionProvider) -> Response:
        page = await exposition.render()
        return Response(content=page.content, media_type=page.media_type)
