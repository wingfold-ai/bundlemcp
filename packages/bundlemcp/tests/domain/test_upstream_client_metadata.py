"""What the gateway remembers about its client at an upstream authorization server."""

from typing import Any

import pytest
from bundlemcp.domain.upstream_oauth.client_identification import ClientIdentification
from bundlemcp.domain.upstream_oauth.upstream_client_metadata import UpstreamClientMetadata
from bundlemcp.domain.upstream_oauth.upstream_grant import UpstreamGrant
from bundlemcp.domain.upstream_oauth.upstream_metadata import UpstreamMetadata

DISCOVERED = UpstreamMetadata(
    authorization_endpoint="https://as.example/authorize",
    token_endpoint="https://as.example/token",
    registration_endpoint="https://as.example/register",
    resource_scopes=["read"],
    issuer="https://as.example",
    resource="https://mcp.example/mcp",
)
GATEWAY = {
    **DISCOVERED.model_dump(exclude_none=True, exclude={"step_up_scopes"}),
    "identification": "metadata_document",
}
STORED_SHAPES: list[dict[str, Any]] = [
    {
        "authorization_endpoint": "https://idp.example/auth",
        "token_endpoint": "https://idp.example/token",
        "identification": "preregistered",
        "grant_type": "client_credentials",
    },
    GATEWAY,
    DISCOVERED.model_dump(exclude_none=True),
    {**GATEWAY, "step_up_scopes": ["admin"]},
    {},
    {"identification": "preregistered", "grant_type": "authorization_code", "x-note": "kept"},
    {"authorization_endpoint": "https://idp.example/auth", "issuer": "https://idp.example"},
]


def _read_by_key(record: dict[str, Any]) -> tuple:
    """What a record means when each key is read with its fallback."""
    both = record.get("authorization_endpoint") and record.get("token_endpoint")
    return (
        ClientIdentification(record.get("identification", ClientIdentification.PREREGISTERED)),
        UpstreamGrant(record.get("grant_type", UpstreamGrant.AUTHORIZATION_CODE)),
        list(record.get("step_up_scopes") or []),
        record.get("issuer") if both else None,
        UpstreamMetadata(**record) if both else None,
    )


def _read_typed(metadata: UpstreamClientMetadata) -> tuple:
    return (
        metadata.identification,
        metadata.grant,
        list(metadata.step_up_scopes),
        metadata.endpoints.issuer if metadata.endpoints else None,
        metadata.remembered_endpoints,
    )


@pytest.mark.parametrize("stored", STORED_SHAPES)
def test_ups25_every_stored_shape_round_trips(stored: dict[str, Any]) -> None:
    """UPS-25: a stored record loads, dumps back to itself, and means what its keys say."""
    metadata = UpstreamClientMetadata.model_validate(stored)
    dumped = metadata.model_dump()

    assert dumped == stored
    assert UpstreamClientMetadata.model_validate(dumped) == metadata
    assert _read_typed(metadata) == _read_by_key(stored)
    assert _read_by_key(dumped) == _read_by_key(stored)


def test_ups25_an_obtained_client_is_stored_like_a_registration() -> None:
    """UPS-25: a client the gateway obtained is stored as the endpoints plus how."""
    metadata = UpstreamClientMetadata.obtained(
        DISCOVERED.model_copy(update={"step_up_scopes": ["dropped"]}),
        ClientIdentification.METADATA_DOCUMENT,
    )

    assert metadata.model_dump() == GATEWAY
    assert not metadata.is_admin_stored
    assert metadata.step_up_scopes == ()


def test_ups34_step_up_merges_in_order_without_duplicates() -> None:
    """UPS-34: demanded scopes are appended once each, and a repeat changes nothing."""
    metadata = UpstreamClientMetadata.model_validate(GATEWAY)

    once = metadata.with_step_up(["audit", "admin", "audit"])
    twice = once.with_step_up(["admin", "export"])

    assert once.step_up_scopes == ("audit", "admin")
    assert twice.step_up_scopes == ("audit", "admin", "export")
    assert twice.with_step_up(["export"]) == twice
    assert twice.model_dump() == {**GATEWAY, "step_up_scopes": ["audit", "admin", "export"]}
    remembered = twice.remembered_endpoints
    assert remembered is not None
    assert remembered.authorization_scope == "read audit admin export"


def test_ups25_admin_configuration_keeps_remembered_endpoints() -> None:
    """UPS-25: an admin's client keeps the discovered endpoints unless both URLs are replaced,
    and keeps the scopes an upstream demanded."""
    gateway = UpstreamClientMetadata.model_validate({**GATEWAY, "step_up_scopes": ["admin"]})

    kept = gateway.configured_by_admin(UpstreamGrant.CLIENT_CREDENTIALS, None, "https://t")
    replaced = gateway.configured_by_admin(
        UpstreamGrant.AUTHORIZATION_CODE, "https://idp/a", "https://idp/t"
    )

    assert kept.is_admin_stored and kept.grant == UpstreamGrant.CLIENT_CREDENTIALS
    assert kept.endpoints == gateway.endpoints
    assert kept.step_up_scopes == ("admin",)
    assert replaced.endpoints is not None
    assert replaced.endpoints.authorization_endpoint == "https://idp/a"
    assert replaced.endpoints.token_endpoint == "https://idp/t"
    assert replaced.endpoints.issuer == "https://as.example"
    assert replaced.model_dump() == {
        **GATEWAY,
        "authorization_endpoint": "https://idp/a",
        "token_endpoint": "https://idp/t",
        "identification": "preregistered",
        "step_up_scopes": ["admin"],
        "grant_type": "authorization_code",
    }
