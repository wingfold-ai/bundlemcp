"""SES-3a: a session belongs to the caller that opened it."""

import uuid

from bundlemcp.domain.access.caller_identity import CallerIdentity
from bundlemcp.domain.access.user import User
from bundlemcp.domain.sessions.session_record import SessionRecord

USER = uuid.uuid4()
KEY = uuid.uuid4()


def _user(user_id: uuid.UUID, email: str | None) -> CallerIdentity:
    return CallerIdentity.oauth_user(
        User(id=user_id, oidc_issuer="http://idp", oidc_sub="alice", email=email)
    )


def _opened_by(identity: CallerIdentity) -> SessionRecord:
    return SessionRecord(
        session_id="s",
        endpoint_name="main",
        bundle_name="main",
        identity=identity,
        protocol_version="2025-11-25",
    )


def test_same_user_owns_session_whatever_the_email():
    record = _opened_by(_user(USER, "a@example.com"))
    assert record.is_owned_by(_user(USER, "b@example.com"))


def test_other_user_does_not_own_session():
    record = _opened_by(_user(USER, None))
    assert not record.is_owned_by(_user(uuid.uuid4(), None))


def test_same_api_key_owns_session():
    record = _opened_by(CallerIdentity.with_api_key(KEY))
    assert record.is_owned_by(CallerIdentity.with_api_key(KEY))


def test_other_api_key_does_not_own_session():
    record = _opened_by(CallerIdentity.with_api_key(KEY))
    assert not record.is_owned_by(CallerIdentity.with_api_key(uuid.uuid4()))


def test_anonymous_session_on_open_endpoint_is_shared_by_anonymous_callers():
    assert _opened_by(CallerIdentity.anonymous()).is_owned_by(CallerIdentity.anonymous())


def test_api_key_does_not_own_a_users_session():
    record = _opened_by(_user(USER, None))
    assert not record.is_owned_by(CallerIdentity.with_api_key(KEY))
