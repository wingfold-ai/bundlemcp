# ADR-0047: Profiles are named for what they change

**Status:** accepted · **Date:** 2026-10-15 · **Amends:** [ADR-0007](0007-endpoint-profiles.md)

## Context

ADR-0007 named two of the three endpoint profiles after the client each was first built for: `claude` and `chatgpt`.
Such a name says nothing about the effect. `claude` changes no tool; it only requires OAuth. `chatgpt` rewrites every
tool's annotations. Neither is specific to its namesake: an OAuth-only endpoint suits any client that signs a person
in, and the rewrite suits any client that is wary of write tools. The names also date: if ChatGPT stops needing the
rewrite, or a second client needs it, the `chatgpt` profile does the wrong thing for its name.

The repo names components for their mechanism, never for a moment in time (the design principles). The profile
identifiers were the visible exception, published through the management API, the bootstrap file and the UI.

## Decision drivers

- An identifier should stay true when the clients change (EP-23).
- No change to what any profile does: its auth-mode rule, its transform and its warning stay as they are.
- An upgrade should need no admin action: stored endpoints keep serving.
- There are no versioned releases or outside deployments yet, so a breaking rename is cheap now and expensive later.

## Decision

- **The identifiers name the effect:** `default`, `oauth_only` (OAuth is the only auth mode; tools pass through) and
  `write_as_read` (every tool is presented as read-only while it still performs its real operation). The preset
  classes follow: `OauthOnlyProfile`, `WriteAsReadProfile`.
- **A hard rename, no aliases.** The management API, the profile listing and bootstrap files accept only the new
  identifiers; `claude` or `chatgpt` is a validation error that lists the accepted values.
- **Stored endpoints are migrated in SQL.** Alembic revision `0009` rewrites `endpoints.profile`, and its downgrade
  reverses it. Nothing in the code knows the former names afterwards.
- **Recommending a client is UI advice, not domain data.** The catalogue's setup steps still recommend `oauth_only`
  for claude.ai and `write_as_read` for ChatGPT. The UI shows the profile warning whenever the listing gives one,
  instead of comparing the profile's name.

## Alternatives considered

- **Keep the old identifiers as aliases for a release.** Softer for scripts, but it keeps the client names in the
  row mapping and the DTOs, and there is no outside caller yet to protect.
- **Map the old values when rows are read**, instead of migrating them. No migration, but the domain then knows the
  former names forever.
- **A two-step rename** (accept both, migrate, then drop) to keep the previous release able to read the rows during a
  rolling update. Correct for a released product; here it costs a release cycle for no deployment that needs it.
- **A `recommended_client` field on each preset.** Would let the API name the client, but puts client names back into
  the domain, which is what this decision removes.

## Consequences

**Positive:**

- A profile's name tells an admin what it does; a client recommendation can change without renaming anything.
- The UI no longer branches on a profile's name, so a future profile with a warning shows it without a UI change.

**Trade-offs:**

- Breaking for every caller and bootstrap file that names `claude` or `chatgpt`.
- Revision `0009` is not readable by the previous release: during a rolling update an old replica fails to validate a
  rewritten row. The deploy guide says to stop the old replicas before starting the new ones for this upgrade.
