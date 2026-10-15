# Tasks

## 1. Domain rule

- [x] 1.1 Add a pure function in `domain/servers/` (a module named for the rule, e.g. `self_reference.py`) that decides
  whether a URL addresses an MCP endpoint of a gateway with a given public base URL: origin equality with a
  case-insensitive host and the default port made explicit, trailing slash ignored, path exactly
  `{public path}/{name}/mcp`; verify with table-driven tests in `tests/domain/` named for BND-5 covering
  `http://localhost:8000/loop-ep/mcp`, upper-case host, explicit `:443`, trailing slash, a public URL with a path
  prefix, a deeper path, another host, and another scheme

## 2. Enforce on membership and URL change

- [x] 2.1 Pass the public base URL into `BundleService` and refuse `set_member` with a `ConflictError` naming BND-5 when
  the member's URL is a self-reference; verify with an application test on the memory fakes and an API test asserting
  `409` and that no membership was stored (BND-5)
- [x] 2.2 In `ServerService.upsert`, when the URL changes on an upstream that is a member of any bundle, run the same
  check before saving; verify with tests that the update answers `409` and leaves the stored URL unchanged, and that
  a non-member may still be registered with such a URL (BND-5)
- [x] 2.3 Wire the public base URL into both services in `main/` and the service providers; verify bootstrap with a
  self-referencing member fails the document (strict mode) with the same message, through a bootstrap test (BND-5)
- [x] 2.4 Document the `409` on both routes if responses are listed in OpenAPI, then run `cd apps/web && npm run
  openapi` and verify `apps/web/openapi.json` and `apps/web/types/api.d.ts` are current

## 3. Documentation

- [x] 3.1 Replace the claim in `docs/manage/bundles.md` with the actual rule (checked on membership and on a member's
  URL change, any `/{name}/mcp` path) and its limit (the gateway reached under another hostname, an internal service
  name or through a proxy is not detectable from the URL); verify `python3 tools/check_docs_links.py` passes
- [x] 3.2 Mention the guard in `docs/manage/servers.md` where a URL change is described, if that page covers it; verify
  the wording matches the scenarios in the delta spec

## 4. Gates

- [x] 4.1 Run `uv run pytest -q`, `uv run ruff check .`, `uv run rumdl check .`, `uv run lint-imports`, the four
  `tools/check_*.py` scripts, and `openspec validate --all --strict`; verify all pass
