"""Which browser origins may use an endpoint from another site (EP-24)."""

import pytest
from bundlemcp.domain.endpoints.endpoint import Endpoint
from bundlemcp.domain.endpoints.endpoint_auth_mode import EndpointAuthMode
from bundlemcp.domain.endpoints.origin_policy import (
    default_allowed_origins,
    normalise_allowed_origins,
    normalise_origin,
    origin_allowed,
)
from pydantic import ValidationError

PUBLIC = "https://gw.example.com"
NONE, OAUTH, API_KEY = EndpointAuthMode.NONE, EndpointAuthMode.OAUTH, EndpointAuthMode.API_KEY


@pytest.mark.parametrize(
    ("entry", "expected"),
    [
        ("https://App.Example", "https://app.example"),
        ("https://app.example/", "https://app.example"),
        ("https://app.example:443", "https://app.example"),
        ("http://app.example:80", "http://app.example"),
        ("http://localhost:3000", "http://localhost:3000"),
        ("http://[::1]:8080", "http://[::1]:8080"),
    ],
)
def test_ep24_origins_are_normalised(entry, expected):
    """EP-24: scheme and host compare case-insensitively; default ports and a slash drop."""
    assert normalise_origin(entry) == expected


@pytest.mark.parametrize(
    "entry",
    [
        "app.example",
        "https://app.example/path",
        "https://app.example?x=1",
        "https://app.example#f",
        "https://user@app.example",
        "ftp://app.example",
        "https://",
        "https://app.example:99999",
    ],
)
def test_ep24_entries_that_are_not_origins_are_rejected(entry):
    """EP-24: an entry with a path, query, fragment, user, other scheme or no host is refused."""
    with pytest.raises(ValueError, match="not an origin"):
        normalise_origin(entry)


def test_ep24_the_wildcard_stands_alone():
    """EP-24: '*' allows every origin and cannot be mixed with entries."""
    assert normalise_allowed_origins(["*"]) == ["*"]
    with pytest.raises(ValueError, match=r"\*"):
        normalise_allowed_origins(["*", "https://app.example"])
    assert normalise_allowed_origins(["https://a.example", "https://A.example/"]) == [
        "https://a.example"
    ]


def test_ep24_defaults_follow_the_auth_modes():
    """EP-24: an open endpoint refuses cross-site browsers; one needing a credential allows any."""
    assert default_allowed_origins([NONE]) == []
    assert default_allowed_origins([OAUTH]) == ["*"]
    assert default_allowed_origins([OAUTH, API_KEY]) == ["*"]
    open_endpoint = Endpoint(
        name="o", bundle_id="00000000-0000-0000-0000-000000000000", auth_modes=[NONE]
    )
    assert open_endpoint.allowed_origins == []
    keyed = Endpoint(name="k", bundle_id="00000000-0000-0000-0000-000000000000")
    assert keyed.allowed_origins == ["*"]


def test_ep24_an_endpoint_refuses_an_invalid_entry():
    with pytest.raises(ValidationError, match="not an origin"):
        Endpoint(
            name="e",
            bundle_id="00000000-0000-0000-0000-000000000000",
            allowed_origins=["https://app.example/path"],
        )


@pytest.mark.parametrize(
    ("origin", "allowed", "expected"),
    [
        ("https://app.example", ["https://app.example"], True),
        ("https://APP.example:443", ["https://app.example"], True),
        ("https://evil.example", ["https://app.example"], False),
        (PUBLIC, [], True),
        ("https://gw.example.com:443", [], True),
        ("null", ["https://app.example"], False),
        ("null", ["*"], True),
        ("https://anything.example", ["*"], True),
        ("garbage", [], False),
    ],
    ids=[
        "listed",
        "listed-normalised",
        "other",
        "own",
        "own-port",
        "null",
        "null-any",
        "any",
        "garbage",
    ],
)
def test_ep24_origin_decision(origin, allowed, expected):
    """EP-24: listed origins and the gateway's own pass; null and others only with '*'."""
    assert origin_allowed(origin, allowed, PUBLIC) is expected
