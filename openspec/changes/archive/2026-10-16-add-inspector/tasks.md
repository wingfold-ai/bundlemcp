# Tasks

## 1. Targets and the use case

- [x] 1.1 Add the `InspectorTarget` union and the operation DTOs in `application/schemas/inspector/`, every field
  described; verify with schema tests that an unknown target kind is rejected (UI-8)
- [x] 1.2 Implement `InspectorService` in `application/inspection/` for upstream and ad-hoc targets through
  `UpstreamClientFactory`, with the upstream OAuth token for shared and per-user upstreams; verify with tests on
  in-process FastMCP servers that stored headers reach the upstream and never appear in a response, and that a
  service key on a per-user upstream gets the documented refusal (UI-8, UI-10)
- [x] 1.3 Verify with a test that an ad-hoc URL resolving to `169.254.169.254` is refused by the egress policy with
  `egress_denied` and nothing is sent (UI-10, SEC-1)

## 2. Endpoint targets through the public path

- [x] 2.1 Add the `GatewayEndpointClientFactory` contract, its in-process ASGI adapter in `infrastructure/fastmcp/`, and
      wire it in `main/`; verify with an API test that listing tools of a write_as_read-profile endpoint returns the
      curated, profile-annotated list a client sees (UI-8)
- [x] 2.2 Verify with a test that a tool call through an endpoint target writes one audit record, and one through an
  upstream target writes none and logs `source=inspector` (UI-11)
- [x] 2.3 Verify `uv run lint-imports` passes: the controller and use case name only contracts

## 3. Management API

- [x] 3.1 Add `InspectorController` with connect, ping, list-tools and the streaming call-tool route, registered in
  `main/app.py`; verify with ASGI tests that progress notifications stream before the result, timings are reported,
  error results are returned as errors, and unauthenticated calls are refused before any target is contacted
  (UI-9, UI-10)
- [x] 3.2 Run `cd apps/web && npm run openapi` and verify the generated files are current

## 4. Admin UI and docs

- [x] 4.1 Replace the placeholder in `apps/web/app/pages/inspector.vue` with the target picker, capability view, tool
  list with schemas, schema-generated form with raw-JSON fallback, confirmation for destructive tools, and the result,
  progress and timing display; update `apps/web/tests/login.spec.ts` and add a Playwright test citing UI-9; verify
  `npm run typecheck` and the UI suite pass
- [x] 4.2 Document the inspector under `docs/manage/` (targets, credentials for endpoint targets, metering and audit of
  endpoint calls) and update `docs/self-hosting/operations.md` and `docs/arc42/11-risks-and-technical-debt.md`; verify
  the docs checks pass
- [x] 4.3 Add the ADR for the management-API inspector proxy with in-process endpoint dispatch; verify
  `python3 tools/check_adr_graph.py` passes

## 5. Gates

- [x] 5.1 Run `uv run pytest -q`, `uv run ruff check .`, `uv run rumdl check .`, `uv run lint-imports`, the four
  `tools/check_*.py` scripts, `cd apps/web && npm run openapi`, and `openspec validate --all --strict`; verify all pass
