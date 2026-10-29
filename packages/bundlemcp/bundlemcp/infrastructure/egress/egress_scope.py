from enum import StrEnum


class EgressScope(StrEnum):
    """How far a gateway-initiated request may reach.

    ``UPSTREAM`` is the operator's egress policy as configured: private
    networks are reachable, because registered servers usually live on one.
    ``PUBLIC`` additionally refuses every address that is not globally
    routable, for fetches a caller can trigger before signing in, whose URL
    the caller chooses.
    """

    UPSTREAM = "upstream"
    PUBLIC = "public"
