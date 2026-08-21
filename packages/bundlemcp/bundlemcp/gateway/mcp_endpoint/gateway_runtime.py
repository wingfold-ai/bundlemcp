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
        runtime_config=None,
        registry=None,
        signals=None,
        upstream_tokens=None,
        public_url="",
        counters=None,
        settings=None,
    ) -> None:
        self.sessions: SessionStore = session_store
        self.metering = metering
        self.audit = audit
        self.client_factory = client_factory
        self.runtime_config = runtime_config  # spec 02 Config accessors (PROT-2 values)
        self.registry = registry  # replica-pinned streams/calls/replies (SES-13)
        self.signals = signals  # cross-replica routing (SES-13)
        self.upstream_tokens = upstream_tokens  # UpstreamTokenStore | None (spec 23)
        self.public_url = str(public_url).rstrip("/")
        self.counters = counters or Counters()  # metrics seam (spec 51)
        self.settings = settings
