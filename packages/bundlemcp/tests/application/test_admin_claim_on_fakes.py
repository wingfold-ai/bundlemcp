"""Admin rights from the configured ID-token claim, decided at every login (AUTH-17)."""

import pytest
from bundlemcp.application.oauth_server.user_provisioning_service import (
    UserProvisioningService,
    VerifiedClaims,
)
from bundlemcp.infrastructure.memory.in_memory_unit_of_work import InMemoryUnitOfWork
from structlog.testing import capture_logs


def provisioning(claim: str = "groups", value: str = "bundlemcp-admin") -> UserProvisioningService:
    return UserProvisioningService(
        InMemoryUnitOfWork(), admin_emails=[], admin_claim=claim, admin_claim_value=value
    )


def login(claims: dict) -> VerifiedClaims:
    return VerifiedClaims(issuer="https://idp", sub="u", claims={"sub": "u", **claims})


@pytest.mark.parametrize(
    ("claims", "expected"),
    [
        ({"groups": ["staff", "bundlemcp-admin"]}, True),
        ({"groups": "bundlemcp-admin"}, True),
        ({"groups": ["staff"]}, False),
        ({}, False),
    ],
    ids=["list-contains", "single-value", "other-group", "no-claim"],
)
async def test_auth17_default_claim_is_the_groups_claim(claims, expected):
    """AUTH-17: by default a groups claim carrying bundlemcp-admin makes an admin."""
    user = await provisioning().provision(login(claims))
    assert user.is_admin is expected


async def test_auth17_a_dotted_path_reaches_keycloak_realm_roles():
    """AUTH-17: realm_access.roles grants the role; the default groups claim no longer does."""
    service = provisioning("realm_access.roles", "gateway-admin")
    admin = await service.provision(login({"realm_access": {"roles": ["gateway-admin"]}}))
    assert admin.is_admin is True
    other = VerifiedClaims(issuer="https://idp", sub="v", claims={"groups": ["bundlemcp-admin"]})
    assert (await service.provision(other)).is_admin is False


@pytest.mark.parametrize(
    "claims",
    [{"realm_access": {"roles": ["viewer"]}}, {"realm_access": "gateway-admin"}, {}],
    ids=["non-matching-value", "path-through-a-non-object", "missing"],
)
async def test_auth17_no_admin_without_the_value_at_the_path(claims):
    service = provisioning("realm_access.roles", "gateway-admin")
    assert (await service.provision(login(claims))).is_admin is False


async def test_auth17_demotion_takes_effect_at_the_next_login():
    """AUTH-17: the same subject without the group is no longer an admin."""
    service = provisioning()
    assert (await service.provision(login({"groups": ["bundlemcp-admin"]}))).is_admin is True
    assert (await service.provision(login({"groups": []}))).is_admin is False


def by_email(*, verified: bool, claims: dict | None = None) -> VerifiedClaims:
    return VerifiedClaims(
        issuer="https://idp",
        sub="u",
        email="admin@example.com",
        email_verified=verified,
        claims={"sub": "u", **(claims or {})},
    )


def email_provisioning() -> UserProvisioningService:
    return UserProvisioningService(
        InMemoryUnitOfWork(),
        admin_emails=["admin@example.com"],
        admin_claim="groups",
        admin_claim_value="bundlemcp-admin",
    )


async def test_auth17_verified_admin_email_is_admin():
    """AUTH-17: a listed email the issuer marks verified grants the role."""
    user = await email_provisioning().provision(by_email(verified=True))
    assert user.is_admin is True


async def test_auth17_unverified_admin_email_is_not_admin():
    """AUTH-17: a listed but unverified email does not grant the role, and is logged without
    the address."""
    with capture_logs() as logs:
        user = await email_provisioning().provision(by_email(verified=False))
    assert user.is_admin is False
    (warning,) = [e for e in logs if e["event"] == "user.admin_email_unverified"]
    assert "admin@example.com" not in str(warning)


async def test_auth17_admin_claim_needs_no_verified_email():
    """AUTH-17: the admin claim grants the role whether or not the email is verified."""
    claims = {"groups": ["bundlemcp-admin"]}
    user = await email_provisioning().provision(by_email(verified=False, claims=claims))
    assert user.is_admin is True
