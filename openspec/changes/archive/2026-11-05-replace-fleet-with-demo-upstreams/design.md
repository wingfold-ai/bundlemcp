# Design

## Context

See [proposal.md](proposal.md). What exists today, read on 2026-11-05:

- **The fleet:** `deploy/seed.fleet.yaml` is `seed.yaml` plus `seo-psi`, `seo-gsc`, `dataforseo` and `hyperframes`,
  bundled as `seo` and `media`. The compose file starts them, with `seaweedfs`, behind `--profile fleet`; three of the
  images are private, and the seed is chosen with `BUNDLEMCP_SEED_FILE`.
- **The fleet tests** (`tests/integration/test_fleet_bundles.py`, marker `fleet`) are skipped in CI. Two of them check
  what `test_smoke.py` already checks with `echo`. The other three are the only tests for discovery through a static
  `authorization` header, for a forwarded bearer introspected back at the gateway, and for `X-MCP-User`, and the last
  only checks that `tools/list` answers, not the header.
- **Exact tool lists:** the `demo` bundle's tools are asserted exactly in the integration suite, the browser scenarios
  and `apps/web/tests/TESTMAP.md`.

## Goals / Non-Goals

**Goals:** every integration test runs in CI; the behaviours the fleet tested are checked more precisely than before;
nothing about the maintainers' own deployment stays in the repository.

**Non-Goals:** testing Google Search Console, DataForSEO or HyperFrames themselves; rewriting git history (the fleet
files hold image names and the published dev key only).

## Decisions

- **One new demo server, not a new tool on `echo`.** The task's plan put a header-echo tool on `echo-mcp` and the
  introspection on a second server. One server does both: the introspecting server sees the injected `X-MCP-User`
  and the mapped headers as well as `echo` would, and adding a tool to `echo` would change the `demo` bundle's tool
  list, which several suites assert exactly. `echo` stays open and unchanged, so the overhead report can still call it
  directly.
- **A bundle and endpoint of its own** (`passthrough`, oauth + api_key), so the `demo`, `claude` and `chatgpt`
  endpoints and their tests are untouched.
- **The server checks every request, not only tool calls.** It introspects in front of the MCP transport and answers
  401 to a bearer that is not active, so a discovery without the static header fails, which is what makes the
  static-header test meaningful.
- **It reports header names, not values,** except `X-MCP-User` and the mapped tenant header; the bearer is reported
  only as present. Nothing secret reaches a test log.
- **The introspection client secret is the dev service key,** passed the way the compose file passed it to `seo-gsc`.
- **AUTH-31 is checked with two callers taking turns** (a signed-in user and an API key) on one endpoint, each
  expecting its own subject on every call. The dev realm signs in one user, and two different bearers are what the
  requirement is about.
- **`BUNDLEMCP_SEED_FILE` is removed** rather than kept as an override: its only use was the fleet seed, and an operator
  already points `BUNDLEMCP_BOOTSTRAP_FILE` at a document of their own.

## Risks / Trade-offs

- The new tests go through the real OAuth login (Keycloak, consent), like `test_oauth_flow.py`, so they share its
  timing. They reuse its helpers rather than a copy.
- Boot-time discovery of `introspect-demo` races its start, as `echo`'s does; CI forces a discovery of both before the
  suite runs.
