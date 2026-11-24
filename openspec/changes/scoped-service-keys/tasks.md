# Tasks

## 1. Keys and storage (AUTH-40)

- [x] 1.1 Add `ApiKeyScope` and `FULL`, `ApiKey.scopes` with `grants`, `may_introspect` and `calls_endpoints`, and
  `Principal.scopes`.
- [x] 1.2 Migration `0018` and the `ApiKeyRow.scopes` column.
- [x] 1.3 `scopes` on `ApiKeyCreate` (only for service keys, known values, de-duplicated) and `ApiKeyRead`; the
  `keys:manage` rule in `ApiKeyService`.
- [x] 1.4 `scopes` on `BootstrapApiKey` and through `BootstrapRunner` (MGMT-10).

## 2. Enforcement (MGMT-23, AUTH-5)

- [x] 2.1 `access=` on route decorators, published as `x-bundlemcp-access`; `ManagementController` refuses routes
  without it and checks it per route; `ManagementAuth(access)` answers 403 outside the key's scopes.
- [x] 2.2 Declare the access of every management route, `/metrics` and the `me` routes.
- [x] 2.3 Introspection needs `introspect` or an unscoped key; MCP endpoints and introspection treat a scoped key
  without `mcp` as no caller.

## 3. Tests

- [x] 3.1 `tests/api/test_scoped_service_keys.py`: the route audit; building a route without access fails; every route
  refuses a key lacking its access and admits one holding it; read and write on bundles; introspection; `mcp`;
  validation and listing; `keys:manage` without escalation; unscoped keys unchanged.
- [x] 3.2 `tests/application/test_bootstrap_api_keys.py`: scoped keys from environment references; scopes refused on
  endpoint keys and unknown scopes refused.

## 4. Web app, API document and docs

- [x] 4.1 Regenerate `apps/web/openapi.json` and `apps/web/types/api.d.ts`; show and choose scopes on the **API keys**
  page.
- [x] 4.2 ADR-0066 and both ADR indexes.
- [x] 4.3 Scopes in the API keys, bootstrap, authentication, glossary, HTTP surface and upstream identity docs.
