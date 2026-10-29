# Proposal

## Why

On 2026-10-29, `pip-audit` (over `uv export`) and `npm audit` (over the lockfiles) reported known vulnerabilities in
locked dependencies. These versions are what CI tests and what the published images ship. The code audit records this
as finding M4.

| Package | Locked | Fixed in | Advisory |
|---|---|---|---|
| `fastmcp` | 4.0.11 | 4.1.2 | GHSA-7xgj-8392-5q4r (authorization metadata changed by server transforms), GHSA-vqqp-x5qm-5qp4 (OAuth client-credentials issuer binding) |
| `authlib` (via fastmcp) | 1.7.2 | 1.9.1 | CVE-2026-96760 (JWS JSON signature bypass), CVE-2026-114614…114620 (empty HMAC key, nonce skip, RFC 7523 audience, JAR fetch, `is_secure_transport`) |
| `dnspython` | 2.8.0 | 2.9.0 | CVE-2026-114605: CPU exhaustion in name decompression |
| `undici` (via nuxt, @nuxt/ui) | 8.11.2 | 8.12.2+ | 8 advisories including TLS validation bypass, cache poisoning and several DoS (high) |
| `node-forge` (via nitropack) | 1.4.0 | > 1.4.0 | GHSA-86w9-cpqp-85rv, RSA PKCS#1 v1.5 signature check (high) |
| `seroval`, `serialize-javascript`, `deepmerge`, `@nuxt/nitro-server` | — | `npm audit fix` | Code/script injection in serialisers, prototype poisoning, route-rule bypass for case-variant paths (moderate) |
| `vite` (via likec4, docs), `zod` (docs) | 8.3.0, 4.6.2 | 8.3.3+, 4.6.6 | `launch-editor` command injection in the dev server, zod (high; build-time only) |

bundlemcp does not use FastMCP's server transforms or its OAuth client-credentials provider, and its own OIDC uses
`joserfc`, not authlib. So the fastmcp and authlib advisories are not known to be exploitable here. They are still
upgraded, because they sit in the core dependency, and ARC-1 requires the latest stable versions anyway.
`certifi` (PYSEC-2026-4320, the distrusted eMudhra roots) was in the audit too and is already fixed on `main` by #155.

## What Changes

- Re-lock the Python workspace so that `fastmcp ≥ 4.1.2` (pulling `authlib ≥ 1.9.1`) and `dnspython ≥ 2.9.0` are
  locked.
- Raise the declared floor in `packages/bundlemcp/pyproject.toml` to `fastmcp>=4.1.2`, so that no resolution can pick a
  vulnerable version.
- Bump `nuxt` to the patched 4.6.x and `@nuxt/ui` to 4.12 in `apps/web`, and re-lock so `npm audit` reports no high or
  moderate vulnerability. The low-severity `deepmerge` advisory (build-time only, via nitropack) has no patched
  release and stays.
- Re-lock `docs/` so `npm audit` reports nothing.
- Bump the example upstreams' `fastmcp` floor to `>=4.1.2` in their Dockerfiles.

No behaviour changes, so this change carries no spec delta (`skip_specs`).

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None. No requirement changes; ARC-1 (latest stable versions) is what this change restores.

## Impact

- **Resolves:** audit finding M4 (2026-10-29). No GitHub issue.
- **Files:**
  - `uv.lock`
  - `packages/bundlemcp/pyproject.toml`
  - `apps/web/package.json` and `apps/web/package-lock.json`
  - `docs/package.json` and `docs/package-lock.json`
  - `examples/echo-mcp/Dockerfile` and `examples/conformance-mcp/Dockerfile`
- **Risk:** fastmcp 4.0 → 4.1 is a minor release. It is exercised by the hermetic suite, the MCP conformance harness
  (`tests/conformance/run_conformance.py`) and the integration suite. Nuxt is a patch release.
- **Docs:** none; CI writes the CHANGELOG entry from the pull request (DEP-12). No ADR.
- **Not covered:** making a dependency audit a CI gate, so this does not recur (audit finding S4, a separate change).
