"""When a stored upstream token counts as expired or due for refresh, at a given instant."""

import uuid
from datetime import UTC, datetime, timedelta

from bundlemcp.domain.upstream_oauth.upstream_oauth_token import UpstreamOAuthToken

NOW = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)
SKEW = timedelta(seconds=60)


def token(*, expires_in: timedelta | None, is_valid: bool = True) -> UpstreamOAuthToken:
    return UpstreamOAuthToken(
        server_id=uuid.uuid4(),
        tokens_encrypted="ciphertext",
        expires_at=None if expires_in is None else NOW + expires_in,
        is_valid=is_valid,
    )


def test_expiry_is_judged_at_the_given_instant():
    fresh = token(expires_in=timedelta(minutes=5))
    assert not fresh.is_expired_at(NOW)
    assert fresh.is_expired_at(NOW + timedelta(minutes=6))
    assert not token(expires_in=None).is_expired_at(NOW + timedelta(days=365))


def test_connected_means_valid_and_unexpired():
    assert token(expires_in=timedelta(minutes=5)).is_connected_at(NOW)
    assert not token(expires_in=timedelta(minutes=5), is_valid=False).is_connected_at(NOW)
    assert not token(expires_in=-timedelta(seconds=1)).is_connected_at(NOW)


def test_expires_within_the_skew_window():
    assert not token(expires_in=SKEW + timedelta(seconds=1)).expires_within(SKEW, NOW)
    assert token(expires_in=SKEW).expires_within(SKEW, NOW)
    assert token(expires_in=-timedelta(seconds=1)).expires_within(SKEW, NOW)
    assert not token(expires_in=None).expires_within(SKEW, NOW)
