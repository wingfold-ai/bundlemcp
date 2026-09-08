"""Egress policy tests (SEC-2)."""

import pytest
from bundlemcp.application.settings.settings import Settings
from bundlemcp.infrastructure.config.settings import EnvSettings
from bundlemcp.infrastructure.egress.egress_policy import EgressDenied, check_url_allowed


def settings(**kwargs) -> Settings:
    return EnvSettings(_env_file=None, **kwargs)


def test_metadata_endpoint_blocked():
    with pytest.raises(EgressDenied):
        check_url_allowed("http://169.254.169.254/latest/meta-data/", settings())


def test_loopback_blocked_by_default():
    with pytest.raises(EgressDenied):
        check_url_allowed("http://127.0.0.1:8000/mcp", settings())


def test_loopback_allowed_when_explicitly_allowed():
    """SEC-2: explicit allow wins (dev convenience)."""
    check_url_allowed("http://127.0.0.1:8000/mcp", settings(egress_allow_cidrs=["127.0.0.0/8"]))


def test_operator_deny_cidr():
    with pytest.raises(EgressDenied):
        check_url_allowed(
            "http://127.0.0.1/mcp",
            settings(egress_deny_cidrs=["127.0.0.0/8"]),
        )


def test_non_http_scheme_rejected():
    with pytest.raises(EgressDenied):
        check_url_allowed("ftp://example.com/x", settings())
