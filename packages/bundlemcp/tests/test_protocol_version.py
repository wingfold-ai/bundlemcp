"""Protocol-version negotiation unit tests (PROT-12)."""

from bundlemcp.gateway.protocol_version import (
    LATEST_PROTOCOL_VERSION,
    SUPPORTED_PROTOCOL_VERSIONS,
    negotiate_version,
)


def test_blank_request_gets_latest():
    assert negotiate_version(None) == LATEST_PROTOCOL_VERSION
    assert negotiate_version("") == LATEST_PROTOCOL_VERSION


def test_exact_supported_version_echoed():
    for v in SUPPORTED_PROTOCOL_VERSIONS:
        assert negotiate_version(v) == v


def test_newer_than_known_offers_latest():
    assert negotiate_version("2099-01-01") == LATEST_PROTOCOL_VERSION


def test_within_window_downgrades_to_highest_supported():
    # between the oldest and newest but not an exact match → highest supported ≤ requested
    assert negotiate_version("2025-09-01") == "2025-06-18"


def test_older_than_window_fails():
    assert negotiate_version("2024-01-01") is None
