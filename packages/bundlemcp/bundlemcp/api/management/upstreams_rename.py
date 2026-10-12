"""The deprecation window of the management API's "servers" paths, renamed to "upstreams"."""

from datetime import date

from bundlemcp.api.http.route_deprecation import RouteDeprecation

# API-8 / SRV-16: at least 180 days from the release that ships /upstreams
UPSTREAMS_RENAME = RouteDeprecation(deprecated_on=date(2026, 10, 12), sunset_on=date(2027, 4, 10))
