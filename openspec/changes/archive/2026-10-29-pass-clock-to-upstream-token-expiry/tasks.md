# Tasks

## 1. Domain takes the instant

- [x] 1.1 Replace `UpstreamOAuthToken.is_expired`, `is_connected` and `expires_within(skew)` with `is_expired_at(now)`,
  `is_connected_at(now)` and `expires_within(skew, now)`, removing the `utcnow` import from the module. Verify with a
  new domain test `tests/domain/test_upstream_oauth_token.py` (expired, not expired, inside and outside the skew window
  at fixed instants), and confirm with `grep -rn "utcnow()" packages/bundlemcp/bundlemcp/domain` that only
  `system_clock.py` and the `default_factory` timestamps remain

## 2. Services read the injected clock

- [x] 2.1 Give `UpstreamTokenService` a required keyword `clock: Clock`, pass it to `UpstreamTokenStorage` (for
  `expires_at` in `save`) and `UpstreamTokenRefresher` (for the skew check), and to the `status` computation. Wire the
  composition root's `clock`. Verify with `uv run lint-imports` and the existing upstream OAuth tests, after updating
  their constructors to pass a `SystemClock`, which keeps their behaviour identical
- [x] 2.2 Add `test_ups28_refresh_happens_inside_the_skew_window` beside the existing refresh tests in
  `tests/infrastructure/test_upstream_oauth.py`: with a `ManualClock`, a token is not refreshed one second outside
  `REFRESH_SKEW` and is refreshed one second inside it. Verify that it passes without sleeping

## 3. Gates

- [x] 3.1 Run `uv run pytest -q`, `uv run ruff check .`, `uv run rumdl check .`, `uv run lint-imports`, the four
  `tools/check_*.py` scripts, `python3 tools/check_spec_ids.py` and `openspec validate --all --strict`; all pass (no
  DTO or route changes)
