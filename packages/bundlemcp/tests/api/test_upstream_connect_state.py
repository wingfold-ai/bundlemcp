"""Who may finish an upstream connect (the upstreams spec)."""

import uuid

from bundlemcp.api.oauth.browser_state.connect_refusal import ConnectRefusal
from bundlemcp.api.oauth.browser_state.upstream_connect_state import UpstreamConnectState
from bundlemcp.domain.access.user import User


def _state(user_id: uuid.UUID | None) -> UpstreamConnectState:
    return UpstreamConnectState(
        server_id=uuid.uuid4(), user_id=user_id, code_verifier="v", redirect_uri="http://gw/cb"
    )


def _user(*, is_admin: bool = False) -> User:
    return User(oidc_issuer="i", oidc_sub=str(uuid.uuid4()), is_admin=is_admin)


def test_ups27_state_completed_only_by_initiator():
    """UPS-27: a per-user connect is finished only by the user it was started for."""
    initiator, other = _user(), _user(is_admin=True)
    state = _state(initiator.id)
    assert state.refusal_for(initiator) is None
    assert state.refusal_for(other) is ConnectRefusal.OTHER_USER
    assert state.refusal_for(None) is ConnectRefusal.NO_SESSION


def test_ups27_shared_state_completed_only_by_admin():
    """UPS-27: the shared connection is finished only by an admin."""
    state = _state(None)
    assert state.refusal_for(_user(is_admin=True)) is None
    assert state.refusal_for(_user()) is ConnectRefusal.NOT_ADMIN
    assert state.refusal_for(None) is ConnectRefusal.NO_SESSION
