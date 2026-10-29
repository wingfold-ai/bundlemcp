"""A user withdrawing their own consents, and consents revoked on deactivation (AUTH-11,
AUTH-25)."""

import uuid
from datetime import UTC, datetime

import pytest
from bundlemcp.application.errors import NotFoundError
from bundlemcp.application.management.user_service import UserService
from bundlemcp.domain.access.user import User
from bundlemcp.domain.oauth.oauth_consent import OAuthConsent
from bundlemcp.domain.shared.system_clock import SystemClock
from bundlemcp.infrastructure.memory.in_memory_unit_of_work import InMemoryUnitOfWork
from bundlemcp.infrastructure.memory.manual_clock import ManualClock


@pytest.fixture
def uow() -> InMemoryUnitOfWork:
    return InMemoryUnitOfWork()


def consent(uow: InMemoryUnitOfWork, user_id: uuid.UUID) -> OAuthConsent:
    granted = OAuthConsent(user_id=user_id, client_id="c", endpoint_id=uuid.uuid4())
    uow.consents.add(granted)
    return granted


async def test_auth11_a_user_revokes_their_own_consent(uow):
    """AUTH-11: the consent is gone from the user's list once they revoke it."""
    me = uuid.uuid4()
    mine = consent(uow, me)
    users = UserService(uow, clock=SystemClock())
    assert [c.id for c in await users.list_consents(me)] == [mine.id]
    await users.revoke_own_consent(me, mine.id)
    assert await users.list_consents(me) == []


async def test_auth11_another_users_consent_is_not_found_and_stays(uow):
    """AUTH-11: a user cannot revoke, or learn of, someone else's consent."""
    me, other = uuid.uuid4(), uuid.uuid4()
    theirs = consent(uow, other)
    users = UserService(uow, clock=SystemClock())
    with pytest.raises(NotFoundError):
        await users.revoke_own_consent(me, theirs.id)
    assert [c.id for c in await users.list_consents(other)] == [theirs.id]


INSTANT = datetime(2026, 10, 1, 9, tzinfo=UTC)


async def test_auth11_revoked_consent_carries_the_clock_instant(uow):
    """AUTH-11: a revoked consent is stamped with the injected clock's instant."""
    me = uuid.uuid4()
    mine = consent(uow, me)
    await UserService(uow, clock=ManualClock(INSTANT)).revoke_own_consent(me, mine.id)
    stored = await uow.consents.get(mine.id)
    assert stored is not None
    assert stored.revoked_at == INSTANT


async def test_auth25_deactivation_revokes_consents_at_the_clock_instant(uow):
    """AUTH-25: deactivating a user revokes each of their consents at the injected clock's
    instant."""
    user = User(oidc_issuer="i", oidc_sub="s")
    uow.users.add(user)
    granted = [consent(uow, user.id), consent(uow, user.id)]
    await UserService(uow, clock=ManualClock(INSTANT)).deactivate(user.id)
    for one in granted:
        stored = await uow.consents.get(one.id)
        assert stored is not None
        assert stored.revoked_at == INSTANT
