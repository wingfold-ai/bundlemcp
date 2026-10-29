# Design

## Context

See [proposal.md](proposal.md). `UpstreamConnectController.connect` (api layer, `api/oauth/controllers/`) already
receives `CurrentSessionUserProvider` and records `user_id` (the user for `?as=me`, `None` for shared) in an
`UpstreamConnectState` held single-use in Valkey. `callback` takes only the state, checks `iss` (RFC 9207), and calls
`UpstreamTokenStorage.complete_authorize(server, pending.user_id, ...)`. It never reads the session.

The session cookie is `SameSite=Lax`. The upstream's redirect to the callback is a top-level GET navigation, so the
browser sends the cookie on the callback.

## Goals / Non-Goals

**Goals:**

- A token is stored only when the browser finishing the flow is the one that is entitled to start it.
- The check runs before the authorization code is redeemed, so a refused callback spends nothing at the upstream.

**Non-Goals:**

- Binding the OIDC login state to the browser (audit S1, a separate change).
- Resuming a connect after login. The state is single-use; the user starts again.

## Decisions

### Check the session user in the callback, in the api layer

`callback` takes `user: CurrentSessionUserProvider`. Right after `states.take(state)` and before the `iss` check and
`complete_authorize`, it applies one rule:

- `pending.user_id is not None`: requires `user is not None and user.id == pending.user_id`.
- `pending.user_id is None` (shared): requires `user is not None and user.is_admin`.

On failure it answers 403 with an HTML page (the existing `PAGE_TEMPLATES`, a new `connect_refused.html`, served with
`PAGE_HEADERS`). The message is the same in every case, so the page does not reveal who started the flow. A
`upstream_oauth.connect_refused` warning is logged with the reason (`no_session`, `other_user`, `not_admin`) and no
user ids. It is written before the server is loaded, so a refused callback costs no database read.

The rule lives on `UpstreamConnectState` as `refusal_for(user) -> ConnectRefusal | None`, so it can be tested
without HTTP and the controller logs the reason without re-deriving it. `ConnectRefusal` is a `StrEnum` beside the
state, in `api/oauth/browser_state/`. The state model is an api-layer browser-state object, which is where this rule
belongs. It is not a domain fact about servers or tokens.

Alternatives considered:

- **A browser-binding cookie set at `/connect`** (hash of the state, checked at the callback). This also defends a
  flow without a session. But both connect modes already require a session at `/connect`, and the session check is
  stricter, because it binds to the *user*, not just to a browser. The cookie can be added later as defence in depth.
- **Re-checking at the application layer** (`complete_authorize` takes the session user). This would spread an
  HTTP-session concept into a use case that is also reached by the client-credentials path, which has no browser.

### Consume the state on refusal

`states.take` already deletes the state. A refused callback therefore cannot be replayed from the right browser later.
That is intended: the attacker's link is spent, and the real user starts a fresh connect.

## Risks / Trade-offs

- [A user whose session expires during a slow upstream consent sees a refusal] → the page tells them to sign in and
  connect again. The session lifetime is far longer than a consent round-trip.
- [Admins who began a shared connect in one browser and finish it in another] → they now have to restart it in one
  browser. This is documented in `docs/manage/servers.md`.

## Migration Plan

No data migration. States written before the deploy carry the same fields and are checked by the same rule. Rollback is
the previous image.
