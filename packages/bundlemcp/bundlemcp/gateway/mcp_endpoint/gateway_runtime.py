from bundlemcp.gateway.metrics import Counters
from bundlemcp.store.sessions import SessionStore


class GatewayRuntime:
    """Per-app gateway wiring (attached to app.state.gateway)."""

    def __init__(
        self,
        *,
        session_store,
        metering,
        audit,
        client_factory,
        public_url="",
        counters=None,
        settings=None,
    ) -> None:
        self.sessions: SessionStore = session_store
        self.metering = metering
        self.audit = audit
        self.client_factory = client_factory
        self.public_url = str(public_url).rstrip("/")
        self.counters = counters or Counters()  # metrics seam (spec 51)
        self.settings = settings
