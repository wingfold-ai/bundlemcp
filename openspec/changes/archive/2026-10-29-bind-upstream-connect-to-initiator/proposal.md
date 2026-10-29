# Proposal

## Why

The upstream connect callback (`/oauth/upstream/callback`) trusts the single-use state alone. It never checks that the
browser finishing the flow belongs to the user who started it. An attacker can start `connect?as=me`, take the upstream
authorize URL from the redirect and get a victim to open it. If the victim has already consented at the upstream, the
upstream redirects straight back, and the gateway stores the **victim's** upstream token under the **attacker's** user.
From then on the attacker calls that upstream's tools as the victim. The shared variant lets any user who gets an admin
to finish a flow overwrite the shared connection. The 2026-10-29 code audit found this (finding M1).

## What Changes

- **Callback bound to the initiator** (UPS-27, modified): the callback requires a signed-in session. For a per-user
  connection, the session user must be the user who started the flow. For the shared connection, the session user must
  be an admin. Otherwise the callback is refused, the state is consumed, and no token is stored and no code is redeemed.
- A callback that arrives without a session (expired, or a different browser) shows a page asking the user to sign in
  and start the connect again. It does not redirect to login and resume, because the state has already been consumed.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `upstreams`: UPS-27 (the connect callback is completed only by the browser session that started it).

## Impact

- **Resolves:** audit finding M1 (2026-10-29). No GitHub issue.
- **Code:** `api/oauth/controllers/upstream_connect_controller.py` (`callback` takes the current session user and
  checks it against the pending state). Nothing changes in `UpstreamConnectState`, the application layer or the
  storage.
- **Behaviour:** a connect started in one browser and finished in another, signed in as someone else or not signed in,
  now fails. Before, it silently succeeded for the initiator.
- **API:** none. The callback is not part of the OpenAPI document (`include_in_schema = False`).
- **Docs:** `docs/manage/servers.md` (connect flow) states that the flow must be finished in the browser that started
  it. No ADR: this enforces a binding the state already implied, rather than making a new architectural decision.
- **Not covered:** binding the admin **login** (OIDC) state to the browser (audit finding S1, a separate change). That
  is a different attack (login CSRF), which this check does not stop on its own.
