"""Entity/constraint tests (ARC-16, ARC-17)."""

import pytest


async def test_settings_env_prefix(monkeypatch):
    """BUNDLEMCP_ env prefix (the architecture spec conventions)."""
    from bundlemcp.infrastructure.config.settings import EnvSettings

    monkeypatch.setenv("BUNDLEMCP_REDIS_URL", "redis://elsewhere:6379/2")
    monkeypatch.setenv("BUNDLEMCP_ADMIN_EMAILS", '["a@example.com"]')
    settings = EnvSettings(_env_file=None)
    assert settings.redis_url == "redis://elsewhere:6379/2"
    assert settings.admin_emails == ["a@example.com"]


def test_scoped_service_key_reaches_only_its_endpoints():
    """AUTH-23: the endpoint scope applies whatever the key's kind."""
    import uuid

    from bundlemcp.domain.access.api_key import ApiKey
    from bundlemcp.domain.access.api_key_kind import ApiKeyKind

    inside, outside = uuid.uuid4(), uuid.uuid4()
    for kind in (ApiKeyKind.ENDPOINT, ApiKeyKind.SERVICE):
        scoped = ApiKey(
            name="k", key_hash="h", key_prefix="p", kind=kind, endpoint_ids=[str(inside)]
        )
        assert scoped.reaches(inside) and not scoped.reaches(outside)
        unscoped = ApiKey(name="k", key_hash="h", key_prefix="p", kind=kind)
        assert unscoped.reaches(outside)


def test_service_error_status_is_inherited():
    """A subclass of a domain error keeps its parent's HTTP status."""
    from bundlemcp.application.errors import ConflictError, OAuthError, ServiceError
    from bundlemcp.domain.oauth.oauth_error_code import OAuthErrorCode

    class NameCollisionError(ConflictError):
        pass

    assert NameCollisionError("x").status == 409
    assert ServiceError("x").status == 500
    assert OAuthError(OAuthErrorCode.INVALID_GRANT).status == 400
    assert OAuthError(OAuthErrorCode.INVALID_CLIENT).status == 401  # RFC 6749 section 5.2
    assert OAuthError(OAuthErrorCode.TOO_MANY_REQUESTS).status == 429


def test_config_values_are_validated_strictly():
    """A stored config value must already have the key's type; nothing is converted."""
    from bundlemcp.domain.config.config_registry import coerce
    from bundlemcp.domain.config.unknown_config_key import UnknownConfigKey

    assert coerce("call_timeout", 30) == 30.0
    assert coerce("reset_timeout_on_progress", False) is False
    assert coerce("session_lifetime", 10) == 10
    for key, value in [
        ("call_timeout", "30"),
        ("reset_timeout_on_progress", 1),
        ("session_lifetime", True),
        ("session_lifetime", 1.5),
    ]:
        with pytest.raises(ValueError, match=key):
            coerce(key, value)
    with pytest.raises(UnknownConfigKey):
        coerce("nope", 1)


@pytest.mark.parametrize("key", ["max_request_bytes", "max_upstream_response_bytes"])
def test_sec7_size_limits_are_bounded(key):
    """SEC-7: a size limit outside 64 KiB to 64 MiB is refused with a message naming the key."""
    from bundlemcp.domain.config.config_registry import KIB, MIB, coerce

    assert coerce(key, 64 * KIB) == 64 * KIB
    assert coerce(key, 64 * MIB) == 64 * MIB
    for value in (64 * KIB - 1, 64 * MIB + 1):
        with pytest.raises(ValueError, match=key):
            coerce(key, value)


def test_sec7_request_limit_keeps_the_shipped_default():
    """SEC-7: the request limit defaults to 4 MiB, the upstream response cap to 16 MiB."""
    from bundlemcp.domain.config.config_registry import DEFAULTS, MIB

    assert DEFAULTS["max_request_bytes"].default == 4 * MIB
    assert DEFAULTS["max_upstream_response_bytes"].default == 16 * MIB
