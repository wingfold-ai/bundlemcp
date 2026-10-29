# Proposal

## Why

`UpstreamOAuthToken.is_expired`, `is_connected` and `expires_within(skew)`
(`domain/upstream_oauth/upstream_oauth_token.py`) read the wall clock through `utcnow()`. Every other time-dependent
entity takes the instant as an argument: `OAuthAccessToken.is_usable_at(now)`,
`OAuthAuthorizationCode.is_redeemable_at(now)`, `DelegatedToken`. The `Clock` protocol says so in its own docstring:
"entities take the instant as an argument instead". Two consequences:

- The domain layer does I/O, which the layer rules forbid.
- The refresh-skew logic cannot be driven by `ManualClock`. Tests of "refresh just before expiry" depend on real time.

`UpstreamTokenStorage.save` computes `expires_at` with `utcnow()` for the same reason. The 2026-10-29 code audit found
this (finding M6).

## What Changes

- `UpstreamOAuthToken` gets `is_expired_at(now)`, `is_connected_at(now)` and `expires_within(skew, now)`. The
  clock-reading property versions are removed.
- `UpstreamTokenService` takes a required `clock: Clock` and passes it to `UpstreamTokenStorage` (which uses it for
  `expires_at`) and to `UpstreamTokenRefresher` (which uses it for the skew check). The composition root passes its
  existing `clock`.
- No behaviour changes: `SystemClock` returns exactly what `utcnow()` did. This change carries no spec delta
  (`skip_specs`).

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None. A pure refactor towards the layer rule. ARC-15 (clock assumptions) is unaffected.

## Impact

- **Resolves:** audit finding M6 (2026-10-29). No GitHub issue.
- **Code:**
  - `domain/upstream_oauth/upstream_oauth_token.py`
  - `application/upstream_oauth/upstream_token_service.py`, `upstream_token_storage.py` and
    `upstream_token_refresher.py`
  - `main/composition_root.py`
  - the test constructors of `UpstreamTokenService` in `tests/application/test_upstream_oauth_on_fakes.py`,
    `test_server_setup_on_fakes.py`, `test_key_reencryption_on_fakes.py` (which builds `UpstreamTokenStorage` directly),
    `tests/infrastructure/test_upstream_oauth.py`, `tests/api/test_upstream_call.py` and `test_server_setup_api.py`
- **API:** none. `UpstreamConnectionStatus.connected` is computed the same way.
- **Docs:** none. No ADR.
- **Not covered:** the other services that read `utcnow()` or `time.time()` directly (`DiscoveryService`,
  `UserService`, the Valkey session store, the tool-call timing), which is audit finding S15. Those live outside the
  domain layer, so they violate no hard rule, and they are left for that change.
