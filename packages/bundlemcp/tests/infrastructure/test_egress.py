"""Egress policy tests (SEC-2)."""

import ipaddress

import pytest
from bundlemcp.application.settings.settings import Settings
from bundlemcp.infrastructure.config.settings import EnvSettings
from bundlemcp.infrastructure.egress.egress_policy import (
    EgressDenied,
    check_url_allowed,
    judge_address,
)
from bundlemcp.infrastructure.egress.egress_scope import EgressScope


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


@pytest.mark.parametrize(
    "addr",
    ["fd00:ec2::254", "::ffff:169.254.169.254", "::ffff:127.0.0.1", "0.0.0.0", "0.1.2.3", "::"],
    ids=["v6-metadata", "mapped-metadata", "mapped-loopback", "unspecified", "zero-net", "v6-any"],
)
def test_sec2_ipv6_mapped_and_unspecified_forms_are_blocked(addr):
    """SEC-2: IPv6 metadata, IPv4-mapped forms and the unspecified addresses are refused."""
    with pytest.raises(EgressDenied):
        judge_address(ipaddress.ip_address(addr), addr, settings())


def test_sec2_neighbouring_ula_addresses_stay_allowed():
    """SEC-2: only the metadata address is blocked, not the private range around it."""
    judge_address(ipaddress.ip_address("fd00:ec2::253"), "x", settings())


def test_sec2_mapped_address_meets_the_operators_ipv4_entries():
    """SEC-2: an IPv4-mapped address is judged as the IPv4 address, for allow and deny entries."""
    deny = settings(egress_deny_cidrs=["10.1.0.0/16"])
    with pytest.raises(EgressDenied):
        judge_address(ipaddress.ip_address("::ffff:10.1.2.3"), "x", deny)
    judge_address(
        ipaddress.ip_address("::ffff:127.0.0.1"), "x", settings(egress_allow_cidrs=["127.0.0.0/8"])
    )


@pytest.mark.parametrize(
    "address",
    [
        "10.0.0.5",
        "172.16.1.1",
        "192.168.1.1",
        "100.64.0.1",
        "192.0.2.1",
        "fc00::1",
        "2001:db8::1",
        "64:ff9b::a00:5",
        "64:ff9b::a9fe:a9fe",
        "2002:a00:5::1",
        "::ffff:10.0.0.5",
    ],
)
def test_auth13_public_scope_refuses_private_ranges(address):
    """AUTH-13: the public scope refuses private, shared, unique-local, documentation and
    translated addresses that the upstream scope would let through."""
    addr = ipaddress.ip_address(address)
    with pytest.raises(EgressDenied):
        judge_address(addr, "client.example", settings(), EgressScope.PUBLIC)


@pytest.mark.parametrize("address", ["8.8.8.8", "2606:4700::1111", "64:ff9b::808:808"])
def test_auth13_public_scope_allows_public_addresses(address):
    """AUTH-13: a globally routable address, or a NAT64 one that translates to it, passes."""
    judge_address(ipaddress.ip_address(address), "client.example", settings(), EgressScope.PUBLIC)


def test_auth13_public_scope_honours_allow_cidrs():
    """AUTH-13: an explicit allow entry still wins in the public scope."""
    allowing = settings(egress_allow_cidrs=["10.0.0.0/24"])
    judge_address(ipaddress.ip_address("10.0.0.5"), "client.example", allowing, EgressScope.PUBLIC)


def test_auth13_upstream_scope_still_allows_private_networks():
    """AUTH-13: the scope the upstream path uses is unchanged."""
    judge_address(ipaddress.ip_address("10.0.0.5"), "upstream", settings())
