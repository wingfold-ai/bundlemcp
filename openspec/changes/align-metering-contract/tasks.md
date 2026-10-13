# Tasks

## 1. Decisions and record

- [ ] 1.1 Record the maintainers' answers to the two Open decisions in the proposal; if PROT-25 is amended or PROT-26
      makes the repeat the contract, revise the deltas (and add PROT-27 for a version bump) before any code, and verify
      `openspec validate align-metering-contract --strict` passes
- [ ] 1.2 Write the ADR (next free number in `docs/adr/`) for the stage chain and the paused-invocation record,
  amending ADR-0042, and verify `python3 tools/check_adr_graph.py` passes

## 2. Metering context

- [ ] 2.1 Add `CredentialHeaders` and verify with unit tests citing PROT-24 that `authorization`, `cookie`,
  `proxy-authorization` and API-key headers are removed and other headers kept
- [ ] 2.2 Add `auth_method`, `profile`, `session_id`, `headers` and `scratch` to `MeterContext` (described fields,
  4 KiB scratch limit) and fill them in `ToolCall`; verify with api tests citing PROT-24 (API-key caller → `api_key`,
  profile and session id present, modern request → `session_id` `None`, scratch from `pre_call` reaches `post_call`)
- [ ] 2.3 Add the optional `scratch` to the HTTP hook's decision and echo it in the `post_call` event; verify with an
  infrastructure test citing PROT-24 and PROT-29 against a fake hook service

## 3. Stage chain

- [ ] 3.1 Add the `ChainStage` contract, the built-in stages and `ToolChain`, and route the `tools/list` handler and
  `ToolCall` through it; verify the existing PROT-25 tests pass unchanged and a new test citing PROT-25 covers the list
  variant (filter, override and profile applied in order)
- [ ] 3.2 Verify `uv run lint-imports` passes with the stages in `application/` naming only contracts and domain rules

## 4. Once per invocation

- [ ] 4.1 Add the `PausedInvocations` contract, its Valkey adapter and in-memory fake with an atomic claim; verify with
  infrastructure tests on fakeredis that two concurrent claims settle once
- [ ] 4.2 Write the record on an `input_required` leg and claim it on retries in `ToolCall` (pass-through retry and
  re-run) so they skip `pre_call`; change `packages/bundlemcp/tests/api/test_mrtr.py` to assert one `pre_call` and
  verify the MRTR tests citing PROT-26 and PROT-18 pass
- [ ] 4.3 Add `InvocationSweeper` with its lease, started from `main/`; verify with an api test citing PROT-26 that an
  abandoned invocation gets exactly one `post_call` `no_result` after its state expires, and a retry at expiry does not
  produce a second one
- [ ] 4.4 Update `docs/integrate/metering-hook.md` (context table, HTTP event bodies, "Calls that pause for input",
  "`pre_call` can fire more than once") and verify `python3 tools/check_docs_links.py` and
  `python3 tools/check_docs_symbols.py` pass

## 5. MRTR for reads

- [ ] 5.1 Extract `InputRequiredBridge` from `ToolCall` and add `method`/`target` to `RequestState` with defaults;
  verify the existing PROT-18 tests pass and a state sealed by the previous field set still unseals
- [ ] 5.2 Bridge `prompts/get` and `resources/read` for modern clients (pass-through and park-and-resume) through
  `MemberFanout`; verify with api tests citing PROT-18 (modern member prompt, handshake member resource, state for
  another method rejected with `-32602`, no metering call)
- [ ] 5.3 Update the protocol pages under `docs/` that say reads are not bridged and verify
  `python3 tools/check_docs_links.py` passes

## 6. Gates

- [ ] 6.1 Run `uv run pytest -q`, `uv run ruff check .`, `uv run rumdl check .` and `uv run lint-imports` (delete
  `.import_linter_cache` first) and verify all pass
- [ ] 6.2 Run `python3 tools/check_docs_links.py`, `check_docs_symbols.py`, `check_docs_settings.py` and
  `check_adr_graph.py` and verify all pass
- [ ] 6.3 Run `cd apps/web && npm run openapi` if a DTO or route changed and verify the generated files are otherwise
  unchanged
- [ ] 6.4 Run `openspec validate --all --strict` and verify it passes
