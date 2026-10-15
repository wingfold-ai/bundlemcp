"""A user withdrawing their own consents (AUTH-11)."""

import uuid

import pytest
from bundlemcp.application.errors import NotFoundError
from bundlemcp.application.management.user_service import UserService
from bundlemcp.domain.oauth.oauth_consent import OAuthConsent
from bundlemcp.infrastructure.memory.in_memory_unit_of_work import InMemoryUnitOfWork


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
    users = UserService(uow)
    assert [c.id for c in await users.list_consents(me)] == [mine.id]
    await users.revoke_own_consent(me, mine.id)
    assert await users.list_consents(me) == []


async def test_auth11_another_users_consent_is_not_found_and_stays(uow):
    """AUTH-11: a user cannot revoke, or learn of, someone else's consent."""
    me, other = uuid.uuid4(), uuid.uuid4()
    theirs = consent(uow, other)
    users = UserService(uow)
    with pytest.raises(NotFoundError):
        await users.revoke_own_consent(me, theirs.id)
    assert [c.id for c in await users.list_consents(other)] == [theirs.id]
