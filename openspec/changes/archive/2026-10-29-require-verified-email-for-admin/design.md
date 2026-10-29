# Design

## Context

See [proposal.md](proposal.md). The login callback (api, `login_controller.py:103`) turns the provider's `OidcClaims`
(domain, `domain/access/oidc_claims.py`) into `VerifiedClaims` (application) and calls
`UserProvisioningService.provision`, whose `is_admin` checks `claims.email in admin_emails` or the admin claim. The
full claim set is already carried in `claims.claims`. `JoseOidcProvider` (infrastructure) builds `OidcClaims` from the
verified ID token.

## Goals / Non-Goals

**Goals:**

- The email path grants admin only on an address the IdP vouches for.
- The admin-claim path is unchanged.

**Non-Goals:**

- An opt-out setting that trusts unverified emails. See Decisions.
- Consulting the userinfo endpoint when the ID token lacks `email_verified`.

## Decisions

### A typed `email_verified` field, not a lookup in the raw claim dict

`OidcClaims` and `VerifiedClaims` gain `email_verified: bool = Field(default=False, ...)`. `JoseOidcProvider` sets it to
true only for the boolean `True` or the string `"true"`. Amazon Cognito has historically sent the string, and a strict
`is True` would demote every Cognito admin for a formatting quirk. Absent means false. `is_admin` becomes
`claims.email_verified and claims.email in admin_emails`, or the unchanged admin-claim rule.

Reading `claims.claims.get("email_verified")` inside the service would work, but it would leave the security decision
on an untyped dict lookup, which is the pattern the repo's conventions rule out. The typed field also makes the
parsing rule testable in one place, the provider.

### No opt-out setting

A `BUNDLEMCP_ADMIN_EMAILS_REQUIRE_VERIFIED=false` escape hatch was considered for IdPs that never send the claim
(Entra ID). It was rejected for two reasons. Those IdPs all support role or group claims, which are a stronger admin
signal than an email anyway. And an opt-out would quietly reopen the takeover on exactly the IdPs where it is easiest.
The docs show how to grant admin through an Entra app role with `BUNDLEMCP_ADMIN_CLAIM=roles`.

### Warn on a listed but unverified email

`provision` logs `user.admin_email_unverified` (warning) when the email is listed but unverified and the claim path did
not grant admin. The event carries the issuer and no email address, consistent with the rule that logs carry no
personal data beyond ids.

## Risks / Trade-offs

- [An Entra-only deployment loses its admins at the next login] → marked **BREAKING** in the CHANGELOG. The
  identity-provider guide shows the app-role setup. Existing sessions keep working until their next login, which
  leaves time to add the role.
- [An IdP that sends `email_verified` only from userinfo] → the role falls back to the admin claim. Fetching userinfo is
  a non-goal and can be added later without changing this rule.

## Migration Plan

Deploy the new image. Before upgrading, operators on IdPs without `email_verified` configure the admin claim. Rollback
is the previous image; nothing is stored differently.
