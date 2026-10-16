## MODIFIED Requirements

### Requirement: DOC-2 Documentation site
`docs/` MUST be a VitePress site (`docs/.vitepress/`, built with `npm run build` in `docs/`, validated in CI) whose
pages are the operator/integrator guides, grouped by reader task:

- **guide/** — what bundlemcp is, the compose quickstart, core concepts.
- **self-hosting/** — production deployment (public URL, reverse proxy, upgrades, backups — fed by
  [deployment](../deployment/spec.md)), the full `BUNDLEMCP_*` and runtime-config reference, identity provider setup,
  the bootstrap file, day-two operations.
- **manage/** — servers, bundles and tool curation, endpoints, API keys, users and consents, the audit log, export
  and import, the inspector; each page shows the UI path and the equivalent management-API calls.
- **connect/** — **claude.md** (an `oauth_only`-profile endpoint + OAuth walkthrough incl. consent), **chatgpt.md** (the
  `write_as_read` profile + the re-annotation warning, [EP-12](../endpoints/spec.md)), **scripts.md** (API-key access
  for scripts/agents), **stdio-sidecar.md** (wrapping a stdio MCP server in a Streamable-HTTP sidecar with a compose
  snippet — the [UPS-7](../upstreams/spec.md) deliverable).
- **integrate/** — for application layers: the management API, the metering hook, identity forwarding + introspection
  for upstream servers ([protocol](../protocol/spec.md)/[management](../management/spec.md)), and the full
  HTTP surface reference.

Pages document only shipped behaviour. A surface that is reserved but not built is named as such in one place, a "Not
part of this release" section of `docs/self-hosting/operations.md`, rather than described as if it existed; with no
such surface, the section is left out.

#### Scenario: Docs build is a CI gate
- **WHEN** a pull request introduces a dead link in a VitePress page
- **THEN** the CI `docs` job fails at "Build the documentation site"

#### Scenario: Unbuilt surfaces are named, not described
- **WHEN** an operator reads `docs/self-hosting/operations.md`
- **THEN** it describes no page of the admin UI as a placeholder, and names a reserved-but-unbuilt surface only in its
  "Not part of this release" section
