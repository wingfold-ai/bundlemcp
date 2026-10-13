# Proposal: fix stale documentation

## Why

The OpenSpec migration rewrote the specs to describe only what is implemented. Several user docs, module READMEs and
docstrings still describe behaviour that was specified but never built, or that changed since. An operator or a
contributor who trusts them is misled: about redirects and cookie scope (a security-relevant claim), about where logs
go, about a `/metrics` export that does not exist, and about modules that were deleted. This change makes them honest
now; the changes that build the missing behaviour update the same text again when they land.

## What Changes

Documentation and docstrings only — no behaviour change, so no spec delta (`skip_specs: true`).

- `docs/self-hosting/deploy.md`: drop "Redirects are not followed" (the MCP client follows them, without an egress
  re-check per hop — say so, until [harden-http-edge](../harden-http-edge/proposal.md) closes it); the admin session
  cookie sets no `Domain` (host-only), only `Secure` follows the public URL's scheme.
- `infrastructure/config/structured_logging.py`: docstrings say stdout; the handler writes stderr. Say stderr (the
  stream decision itself is in [improve-request-observability](../improve-request-observability/proposal.md)).
- `infrastructure/inprocess/counters.py` and `infrastructure/postgres/audit_writer.py`: drop the claimed `/metrics`
  export ([add-prometheus-metrics](../add-prometheus-metrics/proposal.md) builds it).
- `api/mcp/README.md`: replace the deleted modules (`composition.py`, `streams.py`, `signals.py`, `metering.py`,
  `upstream.py`, `_drive_upstream`) with the current ones, and stop claiming `session_lifetime` sets the session TTL
  (it is registered but read by nothing; the TTL is fixed at 24 h).
- `README.md` quickstart step 2: the default seed registers `echo` and `oauth-demo`; the private fleet lives in
  `deploy/seed.fleet.yaml`.
- `domain/sessions/upstream_binding.py`: `identity_key`'s description claims a fingerprint of the caller and forwarded
  credentials; it stores the caller's `sub` only, and nothing reads it.
- `docs/arc42/11-risks-and-technical-debt.md`: remove "Inspector covers tools only" (there is no inspector) and the
  claim that upstream `list_changed` is delivered within an active-call window (it is not delivered at all).
- `docs/manage/audit.md`: the Audit page filters by time range, endpoint, tool and status only (not bundle, server or
  caller); rejections go to logs (there are no metrics yet); the API lists newest first.
- ADR-0013 calls `BUNDLEMCP_INITIAL_SERVICE_KEY` "the MGMT-10 pattern". ADRs are append-only, so it is **left as is**;
  the bootstrap docs note that MGMT-10's key-in-document form is not built (see
  [add-bootstrap-api-keys](../add-bootstrap-api-keys/proposal.md)).

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- None (documentation only).

## Impact

- Files: the docs, READMEs and docstrings listed above. No code paths, API, schema or settings change.
- Overlaps by design: [complete-session-lifecycle](../complete-session-lifecycle/proposal.md) rewrites the
  `session_lifetime` sentence again when the setting works; the observability and metrics changes rewrite their
  docstrings again when they ship. Land this change first; the later ones edit text that is already true.
