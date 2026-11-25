# Changelog

Every release of bundlemcp, newest first. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and versions follow [Semantic Versioning](https://semver.org/). A release that changes the metering-hook protocol
(`METERING_PROTOCOL_VERSION`) says so in its entry, as a breaking change, so a hook author can tell from the changelog
alone whether a release changes the contract their hook implements; an entry that does not mention it leaves the
protocol unchanged. [CONTRIBUTING.md](CONTRIBUTING.md#how-a-release-happens) says how a release happens.

## [0.4.4] - 2026-11-25

### Fixed

- Discovered tool annotations keep their MCP names (`readOnlyHint`, `destructiveHint`, `idempotentHint`,
  `openWorldHint`) instead of being stored and served as snake_case keys, so clients and the admin inspector see the
  hints again, including destructive marking. ([#239](https://github.com/wingfold-ai/bundlemcp/pull/239))
- The `write_as_read` endpoint profile no longer returns both snake_case and MCP-named annotation keys for a discovered
  tool, and keeps `openWorldHint` under its MCP name. ([#239](https://github.com/wingfold-ai/bundlemcp/pull/239))
- Annotation overrides that use the MCP names now replace the discovered values instead of appearing beside them.
  ([#239](https://github.com/wingfold-ai/bundlemcp/pull/239))
- Existing installs need no migration: the next discovery of each server rewrites its stored tools with the correct
  annotation names. ([#239](https://github.com/wingfold-ai/bundlemcp/pull/239))

## [0.4.3] - 2026-11-24

### Added

- Limit a service key to scopes (`introspect`, `read`, `bundles:write`, `endpoints:write`, `upstreams:write`,
  `keys:manage`, `mcp`), so a component gets only the access it needs. A service key without scopes keeps every right,
  so existing keys and `BUNDLEMCP_INITIAL_SERVICE_KEY` are unchanged.
  ([#231](https://github.com/wingfold-ai/bundlemcp/pull/231))
- Set `scopes` when creating a service key through the API, and read them back, sorted and de-duplicated, when a key is
  read or listed. Endpoint keys take no scopes, and an unknown scope or scopes on an endpoint key are refused with 422.
  ([#231](https://github.com/wingfold-ai/bundlemcp/pull/231))
- Accept `scopes` on service-key entries in the bootstrap file's `api_keys`, including `value_from_env` keys. Scopes on
  an endpoint key or an unknown scope fail the file at startup.
  ([#231](https://github.com/wingfold-ai/bundlemcp/pull/231))
- Choose scopes when creating a service key on the admin UI's API keys page, and see what each key may do in a new
  column. ([#231](https://github.com/wingfold-ai/bundlemcp/pull/231))

### Changed

- Every management route now declares the access it needs, and a scoped service key outside its scopes gets 403. Audit,
  export and import, the inspector, logs, users, runtime-settings changes, `/metrics` and the `/api/v1/me` routes stay
  open only to admins and unscoped service keys. ([#231](https://github.com/wingfold-ai/bundlemcp/pull/231))
- Token introspection accepts a service key without scopes or one with the `introspect` scope. A scoped key without it
  gets 401. ([#231](https://github.com/wingfold-ai/bundlemcp/pull/231))
- A scoped service key without the `mcp` scope no longer authenticates MCP calls, and introspecting it as a token
  reports it inactive. ([#231](https://github.com/wingfold-ai/bundlemcp/pull/231))
- A scoped key holding `keys:manage` can only create, activate, deactivate or delete scoped service keys whose scopes it
  holds itself, so it cannot create a full service key or an endpoint key. Scopes cannot be edited after creation:
  create a new key and delete the old one. ([#231](https://github.com/wingfold-ai/bundlemcp/pull/231))
- Add a database migration that adds a `scopes` column to API keys; existing keys keep every right. Downgrading drops
  the column and turns scoped keys into full service keys, so deactivate or delete them first.
  ([#231](https://github.com/wingfold-ai/bundlemcp/pull/231))

### Security

- Give a component that only introspects tokens, or a worker that only maintains bundles, a key that cannot reconfigure
  the gateway. New management routes are denied to scoped keys until they declare the access they need.
  ([#231](https://github.com/wingfold-ai/bundlemcp/pull/231))

## [0.4.2] - 2026-11-19

### Fixed

- A Dependabot pull request whose description quotes a CI-skip marker such as `[skip ci]` no longer fails the
  description check and waits for a manual edit. CI turns the marker into `(skip ci)` and saves the description, so the
  squash commit does not skip CI, the image publish or the release on `main`. Descriptions written by people are still
  refused. ([#226](https://github.com/wingfold-ai/bundlemcp/pull/226))

## [0.4.1] - 2026-11-19

### Fixed

- A Dependabot pull request title longer than 72 characters is now shortened before the title check, so it no longer
  fails CI. The group suffix goes first, then the version updated from, then the directory, and the shortened title is
  saved on the pull request so the squash commit carries it. ([#221](https://github.com/wingfold-ai/bundlemcp/pull/221))
- The end-to-end test of the audit page's successful-call count now waits for the count to stop changing, because the
  gateway writes audit records after it answers. This removes an occasional spurious CI failure.
  ([#221](https://github.com/wingfold-ai/bundlemcp/pull/221))

## [0.4.0] - 2026-11-17

The first public preview. bundlemcp bundles self-hosted MCP servers behind endpoints for claude.ai, ChatGPT and
scripts: an OAuth 2.1 server and API keys in front of them, tool curation per bundle, per-user upstream credentials, an
audit log, a metering hook and sessions that survive a restart. What comes next is on the
[roadmap](https://bundlemcp.dev/roadmap). Until 1.0, a minor release may change the management API, settings or the
bootstrap format; such a change is marked **Breaking** here.

### Fixed

- **Breaking:** Keep upstream credentials from following a moved URL
  ([#208](https://github.com/wingfold-ai/bundlemcp/pull/208))

## [0.3.8] - 2026-11-17

### Added

- Brand the sign-in pages without rebuilding the image: `BUNDLEMCP_AUTH_PAGES_TEMPLATE_DIR` replaces the consent,
  return-to-client, upstream connected or refused, and account deactivated pages by file name, and any page without a
  file keeps the built-in one. ([#205](https://github.com/wingfold-ai/bundlemcp/pull/205))
- Serve your own stylesheets, fonts and images to the sign-in pages from `BUNDLEMCP_AUTH_PAGES_ASSET_DIR`, read-only at
  `/auth-pages/assets/`. Templates build asset URLs with `asset_url('logo.svg')`, and only css, font and image files are
  served. ([#205](https://github.com/wingfold-ai/bundlemcp/pull/205))
- Check every sign-in page at startup: each is rendered once with sample values, so a broken template stops the gateway
  with an error naming the file, before the database or Valkey is opened, instead of failing someone's sign-in.
  ([#205](https://github.com/wingfold-ai/bundlemcp/pull/205))

### Changed

- While an asset directory is configured, the sign-in pages' Content-Security-Policy also allows styles, fonts and
  images from the gateway's own origin. Scripts and other origins stay blocked, and without the setting the policy is
  unchanged. ([#205](https://github.com/wingfold-ai/bundlemcp/pull/205))
- The development proxy now sends `/auth-pages/*` to the gateway.
  ([#205](https://github.com/wingfold-ai/bundlemcp/pull/205))

### Security

- Asset requests that name a directory, a hidden file, an unlisted file type, or a path leaving the asset directory
  (`..`, encoded `..`, absolute, or a symlink pointing outside) answer `404`. Served assets carry `nosniff` and a
  sandboxing Content-Security-Policy. ([#205](https://github.com/wingfold-ai/bundlemcp/pull/205))

## [0.3.7] - 2026-11-17

### Changed

- Upgrade the admin UI to Nuxt 4.6.4 and the Python dependencies dnspython (2.9.2) and the OpenTelemetry packages (api
  and sdk 1.45.2, instrumentation 0.66b2). ([#206](https://github.com/wingfold-ai/bundlemcp/pull/206))

### Security

- Clear the published security advisories in dnspython, OpenTelemetry, Nuxt and its `@nuxt/*` packages, and node-forge
  by upgrading to patched versions. ([#206](https://github.com/wingfold-ai/bundlemcp/pull/206))
- Pin the admin UI's `readdir-glob` to version 4 so the build no longer pulls in a `minimatch` release with a known
  advisory. ([#206](https://github.com/wingfold-ai/bundlemcp/pull/206))

## [0.3.6] - 2026-11-06

### Security

- Update the admin UI's build-time `glob` and `minimatch` dependencies to patched versions, which closes two moderate
  advisories (GHSA-3g3m-2fjr-6pw4 and GHSA-g3hv-75wg-m249). The affected packages are used only when building the web
  UI. ([#189](https://github.com/wingfold-ai/bundlemcp/pull/189))

## [0.3.5] - 2026-10-30

### Changed

- Deleting an upstream while a discovery of it is running now waits for that discovery to finish, on any replica, for at
  most one probe timeout (60 seconds). The delete then removes the upstream together with everything the discovery
  cached. ([#177](https://github.com/wingfold-ai/bundlemcp/pull/177))

### Fixed

- An upstream deleted while a discovery or tool refresh of it was running no longer comes back in the list once the
  refresh finishes. A discovery that finds its upstream gone reports "server not found" and caches no tools, prompts or
  resources for it. ([#177](https://github.com/wingfold-ai/bundlemcp/pull/177))
- A rename or configuration change saved while a discovery is running is no longer undone when the discovery finishes.
  Discovery now updates only what it found out: capabilities, protocol revision, health, connection state and last
  discovery time. ([#177](https://github.com/wingfold-ai/bundlemcp/pull/177))
- The health status that live calls record no longer overwrites a concurrent rename or configuration change, and no
  longer re-creates a deleted upstream. ([#177](https://github.com/wingfold-ai/bundlemcp/pull/177))

## [0.3.4] - 2026-10-30

### Changed

- A tool refresh can now wait up to one probe timeout (60 s) behind a discovery of the same server that is already
  running, such as the background probe a save starts. It then reports a fresh result instead of failing.
  ([#176](https://github.com/wingfold-ai/bundlemcp/pull/176))
- A write that collides with a concurrent change on a uniqueness rule is now answered with 409 and a message saying it
  can be retried. On MCP paths the answer is a JSON-RPC error.
  ([#176](https://github.com/wingfold-ai/bundlemcp/pull/176))

### Fixed

- A tool refresh sent right after saving an upstream, or on two replicas at once, no longer fails with a 500 and a
  dropped connection. Discoveries of one server now run one after another on every replica, and each tool is stored
  once. ([#176](https://github.com/wingfold-ai/bundlemcp/pull/176))
- The admin UI no longer discards unsaved edits when the page reads the data again. This covers bundle details, upstream
  configuration, upstream OAuth settings, endpoint configuration, prompt and resource curation, and settings values.
  Fields you haven't touched still follow the gateway. ([#176](https://github.com/wingfold-ai/bundlemcp/pull/176))
- Secret inputs on the upstream configuration card are cleared after a successful save.
  ([#176](https://github.com/wingfold-ai/bundlemcp/pull/176))
- The inspector's argument form no longer resets when the tool list is read again. It resets only when you pick a
  different tool or the tool's input schema changes. ([#176](https://github.com/wingfold-ai/bundlemcp/pull/176))
- Pausing the live log page now drops a backlog load that is still in flight, so no entries appear on a paused page.
  Resuming loads them. ([#176](https://github.com/wingfold-ai/bundlemcp/pull/176))

## [0.3.3] - 2026-10-30

### Added

- The upstream rename card now reports a name that is already taken before anything is sent, as the bundle and endpoint
  rename cards do. ([#173](https://github.com/wingfold-ai/bundlemcp/pull/173))
- The admin UI's pure logic now has a Vitest suite, run with `npm test`.
  ([#173](https://github.com/wingfold-ai/bundlemcp/pull/173))
- CI now runs the whole admin UI browser suite against the core stack, and keeps the Playwright report when it fails.
  ([#173](https://github.com/wingfold-ai/bundlemcp/pull/173))

### Changed

- The bundle, upstream and endpoint detail pages show a failed action's error on the card that ran it, whether
  validation or the API refused it. A failed page load still shows at the top of the page.
  ([#173](https://github.com/wingfold-ai/bundlemcp/pull/173))

### Fixed

- The inspector's streamed tool call now gets the same handling of an expired session (401) or a lost admin role (403)
  as other admin UI calls. ([#173](https://github.com/wingfold-ai/bundlemcp/pull/173))

## [0.3.2] - 2026-10-29

### Changed

- `prompts/list`, `resources/list` and `resources/templates/list` now ask their live members at the same time, so a list
  takes as long as its slowest member instead of the sum of all of them. Each member still receives one request, and the
  merged result keeps member order and first-wins de-duplication.
  ([#171](https://github.com/wingfold-ai/bundlemcp/pull/171))
- The order of steps in a tool call no longer depends on `assert` statements, which Python strips under `-O`. Running
  the gateway with optimisations enabled can no longer fail partway through a request because of a missing step.
  ([#171](https://github.com/wingfold-ai/bundlemcp/pull/171))

### Fixed

- A member whose `resources/read` fails is now logged with its cause, so the failure can be diagnosed from the logs.
  ([#171](https://github.com/wingfold-ai/bundlemcp/pull/171))

## [0.3.1] - 2026-10-29

### Added

- After the gateway re-opens a lost `subscriptions/listen` stream to a modern member, it treats every list it listens
  for as changed and reports an update for every watched resource. Changes made while the stream was down now reach
  clients; the first open of a stream and a change of its filter refetch nothing.
  ([#170](https://github.com/wingfold-ai/bundlemcp/pull/170))

### Changed

- A member's own `_meta` is no longer relayed to clients on log messages and resource updates that arrive between calls.
  Clients receive the level, logger and data, or the resource URI, and nothing else.
  ([#170](https://github.com/wingfold-ai/bundlemcp/pull/170))
- After a modern member's listen stream is re-opened, clients may see a list change and a resource update that carry no
  new content. Clients treat both as a signal to fetch again.
  ([#170](https://github.com/wingfold-ai/bundlemcp/pull/170))
- Resource subscriptions to members on the handshake era are sent as explicit `resources/subscribe` and
  `resources/unsubscribe` requests. They no longer go through SDK helpers that the SDK marks deprecated, so a future SDK
  that drops the helpers does not break them. ([#170](https://github.com/wingfold-ai/bundlemcp/pull/170))

### Fixed

- A list change or resource update that a modern member made while its listen stream was down is no longer lost when the
  stream is re-opened. ([#170](https://github.com/wingfold-ai/bundlemcp/pull/170))

## [0.3.0] - 2026-10-29

### Changed

- **Breaking:** ["Reads and exports now return `protocol_mode: \"session\"` where they returned `\"legacy\"`, so update
  any client or script that compares against `\"legacy\"`. Writes that send `\"legacy\"` keep working. An export taken
  from this release that contains a session-mode upstream cannot be imported into the previous release, which rejects
  `session`. Do not move export documents backwards."]. ([#168](https://github.com/wingfold-ai/bundlemcp/pull/168))
- The handshake-only `protocol_mode` is now called `session`. Reads, exports, the OpenAPI schema and the admin UI use
  `session`, and the schema lists `auto` and `session` as an enum beside the pinned revision date pattern.
  ([#168](https://github.com/wingfold-ai/bundlemcp/pull/168))
- Every write (API, bootstrap and import) still accepts `legacy` as a deprecated alias of `session`.
  ([#168](https://github.com/wingfold-ai/bundlemcp/pull/168))
- A logged exception now carries its traceback in an `exception` field in both `json` and `text` formats. Before, `json`
  logged only `"exc_info": true`. ([#168](https://github.com/wingfold-ai/bundlemcp/pull/168))
- Audit pages now break timestamp ties by id descending in every repository, so the order of records stamped in the same
  microsecond is consistent. ([#168](https://github.com/wingfold-ai/bundlemcp/pull/168))

### Fixed

- Logged tracebacks in `text` format no longer print each frame's local variables, which could expose a token or
  decrypted secret on stderr. ([#168](https://github.com/wingfold-ai/bundlemcp/pull/168))
- A logged validation error no longer includes the input it rejected, and database errors no longer include the bound
  statement parameters. ([#168](https://github.com/wingfold-ai/bundlemcp/pull/168))
- Failed discovery listings, completion lookups, secret re-encryption and live-log publishing now log the exception that
  caused the failure. ([#168](https://github.com/wingfold-ai/bundlemcp/pull/168))
- Session records, paused invocations, discovery timestamps and user consent revocation now read the gateway's injected
  clock instead of the wall clock. ([#168](https://github.com/wingfold-ai/bundlemcp/pull/168))

### Security

- Logged exceptions can no longer leak frame local variables, rejected validation input or SQL statement parameters, in
  either log format. This also covers the Alembic migration engine.
  ([#168](https://github.com/wingfold-ai/bundlemcp/pull/168))

## [0.2.2] - 2026-10-29

### Added

- Encrypt servers' static header values (bearer tokens, API keys) at rest under `BUNDLEMCP_TOKEN_ENCRYPTION_KEYS` when
  it is set, with the same key rotation as upstream tokens. API responses, export/import and upstream calls are
  unchanged. ([#167](https://github.com/wingfold-ai/bundlemcp/pull/167))
- Encrypt static header values that were stored in plaintext before a key was configured, in the background
  re-encryption pass, and report how many as `sealed` in the `token_encryption.swept` log.
  ([#167](https://github.com/wingfold-ai/bundlemcp/pull/167))
- Log `static_headers.plaintext` at startup, with the server count and a `reason` (`no_encryption_key` or
  `awaiting_reencryption_pass`), when servers still hold plaintext header values. It never logs names or values.
  ([#167](https://github.com/wingfold-ai/bundlemcp/pull/167))

### Changed

- Admin login can be finished only in the browser that started it. A login in flight during the upgrade, or finished in
  another browser, fails once with `400` and has to be started again.
  ([#167](https://github.com/wingfold-ai/bundlemcp/pull/167))
- Starting a second login in the same browser replaces the first, so only the latest login can finish.
  ([#167](https://github.com/wingfold-ai/bundlemcp/pull/167))
- Every path under `/oauth/` refuses a request body over a fixed 64 KiB with `413` and an `invalid_request` error.
  Declared and streamed bodies are both checked, whatever the runtime request limit is.
  ([#167](https://github.com/wingfold-ai/bundlemcp/pull/167))
- Dynamic client registration refuses oversized metadata with `invalid_client_metadata`, naming the field: more than 10
  redirect URIs, a redirect URI over 2048 characters, a `client_name` over 200, a `scope` over 1000, or more than 10
  `grant_types` or `response_types`. ([#167](https://github.com/wingfold-ai/bundlemcp/pull/167))
- Static headers that no configured key can decrypt are kept through unrelated edits of the server, so restoring the key
  recovers them. Until then the server is called without them.
  ([#167](https://github.com/wingfold-ai/bundlemcp/pull/167))

### Security

- Close a login CSRF hole: `/login` sets a short-lived binding cookie (`__Host-bmcp_login` and `Secure` on https,
  `bmcp_login` on plain http). `/login/callback` signs nobody in without it, so a callback link handed to a victim no
  longer signs them in as the attacker. ([#167](https://github.com/wingfold-ai/bundlemcp/pull/167))
- Bound request bodies on the unauthenticated `/oauth/` routes, including `POST /oauth/register`, so an anonymous caller
  cannot make the gateway read and store unbounded data. ([#167](https://github.com/wingfold-ai/bundlemcp/pull/167))
- Stop leaking static header credentials through database dumps and backups: with an encryption key configured, their
  values are no longer stored in plaintext. ([#167](https://github.com/wingfold-ai/bundlemcp/pull/167))

## [0.2.1] - 2026-10-29

### Added

- Add `deploy/stack.sh secrets` (`make secrets`), which generates any development secret `deploy/.env` lacks, or still
  holds at its published value, without starting the stack. ([#163](https://github.com/wingfold-ai/bundlemcp/pull/163))

### Changed

- The development stack's host ports (gateway, web app, Keycloak, the demo upstream and the other side services) listen
  on `127.0.0.1` only, so they are no longer reachable from the local network. To open them on purpose, pass your own
  compose file after the stack's. ([#163](https://github.com/wingfold-ai/bundlemcp/pull/163))
- The quickstart now moves to a tunnel with `deploy/stack.sh rebuild`, and the setups page describes the generated
  secrets, the refusal message and how to open the stack to a trusted LAN.
  ([#163](https://github.com/wingfold-ai/bundlemcp/pull/163))
- Plain `docker compose up` without `deploy/.env` still starts with the development values, which are now reachable from
  the local machine only. ([#163](https://github.com/wingfold-ai/bundlemcp/pull/163))

### Security

- `deploy/stack.sh` generates the initial service key, the token encryption key and the Keycloak admin console password
  into `deploy/.env` (mode 0600) before every start, when they are missing or still hold the published development
  values. The service key is printed once. Values you set yourself are never touched.
  ([#163](https://github.com/wingfold-ai/bundlemcp/pull/163))
- The token encryption key is rotated rather than replaced: the new key goes first and the published one stays second,
  so stored upstream tokens remain readable and are re-encrypted.
  ([#163](https://github.com/wingfold-ai/bundlemcp/pull/163))
- In the `quick` and `ngrok` tunnel modes, the script checks the running gateway after startup. If it still accepts the
  service key published in the repository, which an old data volume can keep, it stops the tunnel and proxy and exits
  with status 3. It explains how to revoke the key or rebuild.
  ([#163](https://github.com/wingfold-ai/bundlemcp/pull/163))
- Closes a hole where a default `make up` published a gateway through a public tunnel with a repository-known service
  key, which gave full management access including secret export.
  ([#163](https://github.com/wingfold-ai/bundlemcp/pull/163))

## [0.2.0] - 2026-10-29

### Fixed

- **Breaking:** Grant admin by email only when the email is verified
  ([#161](https://github.com/wingfold-ai/bundlemcp/pull/161))

## [0.1.20] - 2026-10-29

### Added

- Add `BUNDLEMCP_CLIENT_METADATA_DOCUMENTS_ENABLED` (default `true`). When it is `false`, an `https://` client id is
  refused as an unknown client without any outbound request, and the authorization server metadata reports
  `client_id_metadata_document_supported: false`. ([#162](https://github.com/wingfold-ai/bundlemcp/pull/162))

### Changed

- A client whose metadata document is hosted on a private address is no longer fetched unless that address is allowed in
  `BUNDLEMCP_EGRESS_ALLOW_CIDRS`. Public clients such as claude.ai and ChatGPT are unaffected.
  ([#162](https://github.com/wingfold-ai/bundlemcp/pull/162))

### Fixed

- A failed or invalid client metadata document is remembered for 60 seconds, so repeated authorize requests for the same
  URL no longer cost a full fetch each time. A remembered failure is reported with the same error as a fresh one.
  ([#162](https://github.com/wingfold-ai/bundlemcp/pull/162))
- A slow or endless client metadata document can no longer hold a worker. The fetch now has a 5-second deadline for the
  whole request and refuses a body over 16 KiB, whether or not a length is declared.
  ([#162](https://github.com/wingfold-ai/bundlemcp/pull/162))

### Security

- Close an SSRF hole on `/oauth/authorize`. Fetching a client ID metadata document before sign-in now reaches only
  globally routable addresses. Private, CGNAT, unique-local, documentation, 6to4 and NAT64 addresses that translate to
  non-public IPv4 are refused. Anyone on the internet can no longer make the gateway send requests into its private
  network or time the answers. ([#162](https://github.com/wingfold-ai/bundlemcp/pull/162))
- The public-only rule is enforced at connect time on the address actually dialled, so DNS rebinding cannot get around
  it. ([#162](https://github.com/wingfold-ai/bundlemcp/pull/162))

## [0.1.19] - 2026-10-29

### Changed

- An upstream connect has to be finished in the same browser, and under the same gateway account, that started it. A
  connect started in one browser and finished in another, or after the gateway session ended, now fails and must be
  started again. ([#160](https://github.com/wingfold-ai/bundlemcp/pull/160))

### Security

- The upstream connect callback now checks who is finishing the flow. A per-user connect must be finished by the
  signed-in user it was started for, and the shared connection by an admin. This closes a hole where a forwarded
  authorize link could store a victim's upstream token under an attacker's account, or let a non-admin overwrite the
  shared connection. ([#160](https://github.com/wingfold-ai/bundlemcp/pull/160))
- A refused connect callback answers 403 with a page asking the user to sign in and connect again. The upstream code is
  not redeemed, no token is stored, and the single-use state is spent so the link cannot be retried.
  ([#160](https://github.com/wingfold-ai/bundlemcp/pull/160))
- Refused connect callbacks are logged as an `upstream_oauth.connect_refused` warning with the reason (`no_session`,
  `other_user` or `not_admin`) and no user ids. ([#160](https://github.com/wingfold-ai/bundlemcp/pull/160))

## [0.1.18] - 2026-10-29

### Changed

- The minimum supported `fastmcp` is now 4.1.2, and the example upstream images (`echo-mcp`, `conformance-mcp`) install
  `fastmcp>=4.1.2`. ([#159](https://github.com/wingfold-ai/bundlemcp/pull/159))

### Security

- Upgrade `fastmcp` to 4.1.4, closing GHSA-7xgj-8392-5q4r and GHSA-vqqp-x5qm-5qp4. bundlemcp does not use the affected
  server transforms or OAuth client-credentials provider, so neither is known to be exploitable here.
  ([#159](https://github.com/wingfold-ai/bundlemcp/pull/159))
- Upgrade `authlib` (pulled in by `fastmcp`) to 1.9.1, closing CVE-2026-96760 and CVE-2026-114614 to CVE-2026-114620.
  bundlemcp's own OIDC does not use `authlib`. ([#159](https://github.com/wingfold-ai/bundlemcp/pull/159))
- Upgrade `dnspython` to 2.9.0, closing CVE-2026-114605, a CPU exhaustion in name decompression.
  ([#159](https://github.com/wingfold-ai/bundlemcp/pull/159))
- Upgrade Nuxt to 4.6.3 and `@nuxt/ui` to 4.12 in the admin UI, and refresh its lockfile. This closes the high
  advisories in `undici` (TLS validation bypass, cache poisoning, DoS) and `node-forge`, plus advisories in `seroval`,
  `serialize-javascript` and a Nitro route-rule bypass. One low-severity build-time advisory in `deepmerge` remains
  because it has no patched release. ([#159](https://github.com/wingfold-ai/bundlemcp/pull/159))
- Refresh the docs site's lockfile, closing the `vite`/`launch-editor` and `zod` advisories.
  ([#159](https://github.com/wingfold-ai/bundlemcp/pull/159))

## [0.1.17] - 2026-10-22

### Changed

- The gateway and example server images move to Python 3.14.9, which ships a patched pip, and the gateway image builds
  with uv 0.13.5. ([#155](https://github.com/wingfold-ai/bundlemcp/pull/155))
- Building from source now requires uv 0.13.4 or newer; an older uv refuses to work on the project.
  ([#155](https://github.com/wingfold-ai/bundlemcp/pull/155))

### Security

- The gateway no longer trusts the distrusted eMudhra emSign CAs, which were found to use insecure private keys.
  `certifi` is updated to 2026.10.19 and held at that version or newer, which closes a way to intercept outbound TLS
  connections to upstreams and other hosts. ([#155](https://github.com/wingfold-ai/bundlemcp/pull/155))
- The gateway and example images no longer ship a pip or uv that trust the distrusted eMudhra emSign CAs. Rebuild and
  redeploy your images to pick up the fix. ([#155](https://github.com/wingfold-ai/bundlemcp/pull/155))

## [0.1.16] - 2026-10-16

### Added

- Serve `prompts/list`, `resources/list` and `resources/templates/list` from the listing stored at the server's last
  discovery, when every caller may be shown the same listing. Connecting a client no longer wakes a member that scales
  to zero. `prompts/get`, `resources/read`, subscriptions and completions still ask the member.
  ([#150](https://github.com/wingfold-ai/bundlemcp/pull/150))
- Add a per-server `listing_snapshot` setting with the values `auto` (default), `shared` and `live`. It is available on
  the upstream API, the export/import/bootstrap document, the registration form and the upstream page. Use `shared` for
  servers on the gateway's own network or FastMCP servers, whose listings `auto` does not share. Changing the setting
  does not probe the server. ([#150](https://github.com/wingfold-ai/bundlemcp/pull/150))
- Discovery stores each member's prompts, resources and resource templates in full, in the member's order, together with
  the cache scope the server sent. Bundles' clients are told to list prompts or resources again when a stored listing
  changes. ([#150](https://github.com/wingfold-ai/bundlemcp/pull/150))

### Changed

- A member's `prompts/list_changed` or `resources/list_changed` notification now re-discovers the member before clients
  are told, so a client that lists again sees the new listing.
  ([#150](https://github.com/wingfold-ai/bundlemcp/pull/150))
- A member that is down still contributes its last stored prompts and resources to the lists, as its tools already do.
  ([#150](https://github.com/wingfold-ai/bundlemcp/pull/150))
- Existing servers are listed live until their next discovery, because upgrading does not probe them. Run
  `:refresh-tools` once per server, or wait for the periodic refresh. A member whose lists change without a
  `list_changed` the gateway hears keeps its old listing until its next discovery; set `live` on it to restore the
  previous behaviour. ([#150](https://github.com/wingfold-ai/bundlemcp/pull/150))

### Security

- A listing marked `private` by its server is never shared between callers under `auto`. An unscoped listing is shared
  only for servers that are sent nothing depending on the caller: no forwarded headers, no identity header, and no
  per-user or delegated token. ([#150](https://github.com/wingfold-ai/bundlemcp/pull/150))

## [0.1.15] - 2026-10-16

### Added

- A built-in Inspector page in the admin UI replaces the placeholder. Connect to a registered upstream, an endpoint of
  this gateway or any URL with headers, see the server's info, protocol revision and capabilities, ping it, list its
  tools with their schemas and call them. ([#149](https://github.com/wingfold-ai/bundlemcp/pull/149))
- Tool calls in the Inspector get a form built from the tool's input schema, with a raw-JSON toggle and a confirmation
  for tools marked `destructiveHint`. They show progress as it arrives, then the result or error, with connecting and
  call times reported separately. ([#149](https://github.com/wingfold-ai/bundlemcp/pull/149))
- Four management API routes back the Inspector: `POST /api/v1/inspector:connect`, `:ping`, `:list-tools` and
  `:call-tool`. `:call-tool` answers with Server-Sent Events, a `progress` event per notification and then one `result`
  or `failure`. ([#149](https://github.com/wingfold-ai/bundlemcp/pull/149))
- Inspecting an endpoint goes through its public path, so its authentication, profile, curation, metering and audit
  apply, and the tool list matches what its clients see. Enter an API key or OAuth access token for the endpoint; it is
  used for that request only. Calls through an endpoint are metered like any client's, so use a test key or endpoint if
  they may be billed. ([#149](https://github.com/wingfold-ai/bundlemcp/pull/149))
- The demo `echo-mcp` server gains a `countdown` tool that reports progress.
  ([#149](https://github.com/wingfold-ai/bundlemcp/pull/149))

### Changed

- The operations guide no longer has a "Not part of this release" section, since every reserved surface now exists. New
  Inspector docs cover targets, credentials, and how calls are logged, audited and metered.
  ([#149](https://github.com/wingfold-ai/bundlemcp/pull/149))

### Security

- Stored upstream credentials stay on the gateway when inspecting: the management API proxies every Inspector request,
  so no secret reaches the browser and no target needs CORS. A credential value a target echoes back is redacted.
  ([#149](https://github.com/wingfold-ai/bundlemcp/pull/149))
- Ad-hoc URLs in the Inspector go through the egress policy. A URL in a blocked range, such as `169.254.169.254`, is
  refused with `egress_denied` and nothing is sent. ([#149](https://github.com/wingfold-ai/bundlemcp/pull/149))
- Upstream and ad-hoc Inspector calls are logged with `source=inspector` and are not audited. A service key cannot
  inspect a per-user OAuth upstream and gets `409`. ([#149](https://github.com/wingfold-ai/bundlemcp/pull/149))

## [0.1.14] - 2026-10-16

### Added

- The admin UI's Live logs page now shows every replica's events in one view: it loads the recent entries, then follows
  new ones live. It filters by level, text, upstream and endpoint, pauses and resumes from the last entry shown, shows
  which replica wrote each line, and indicates the connection state.
  ([#148](https://github.com/wingfold-ai/bundlemcp/pull/148))
- `GET /api/v1/logs` returns recent live log entries filtered by `level`, `q`, `upstream` and `endpoint`. `GET
  /api/v1/logs/stream` serves the same entries as Server-Sent Events, resuming from `Last-Event-ID` or `since`, and
  answers `429` when a replica already holds too many open streams.
  ([#148](https://github.com/wingfold-ai/bundlemcp/pull/148))
- Add `BUNDLEMCP_LIVE_LOG_LEVEL` (default `INFO`) to set the minimum severity copied to the live log view. An event must
  also pass `BUNDLEMCP_LOG_LEVEL`. ([#148](https://github.com/wingfold-ai/bundlemcp/pull/148))

### Changed

- Each replica copies its log events into one capped Valkey stream, `bmcp:logs`, holding about the newest 10,000
  entries. The buffer is ephemeral and safe to delete, so use your container platform's log stack for history.
  ([#148](https://github.com/wingfold-ai/bundlemcp/pull/148))
- At the default `INFO` level every access line becomes a batched write to Valkey, and each open live log view holds a
  blocking read on Valkey for up to ten seconds at a time. On a very busy gateway, raise `BUNDLEMCP_LIVE_LOG_LEVEL`.
  ([#148](https://github.com/wingfold-ai/bundlemcp/pull/148))

### Security

- Live log entries are exactly the process log's already-redacted lines, so they never contain API keys, tokens, header
  values or tool arguments. ([#148](https://github.com/wingfold-ai/bundlemcp/pull/148))

## [0.1.13] - 2026-10-16

### Added

- Curate a bundle's member prompts and resources like tools: hide an entry from one bundle without disabling the whole
  membership, or present another title or description. The name, URI, arguments and content stay the member's.
  ([#146](https://github.com/wingfold-ai/bundlemcp/pull/146))
- Manage member curation through `GET` and `PUT` on `/api/v1/bundles/{name}/member-prompts` and
  `/api/v1/bundles/{name}/member-resources`, and through new *Member prompts* and *Member resources* cards on the bundle
  page. ([#146](https://github.com/wingfold-ai/bundlemcp/pull/146))
- Discovery caches the names or URIs, titles and descriptions of members that advertise prompts or resources, never
  prompt messages or resource content, so there is something to curate. The cache keeps at most 500 entries per server
  and kind, and a longer listing is logged as `discovery.listing_truncated`. Entries a member stops listing are marked
  stale and keep their curation. ([#146](https://github.com/wingfold-ai/bundlemcp/pull/146))

### Changed

- A disabled member prompt or resource is left out of `prompts/list` and `resources/list` for that bundle. `prompts/get`
  and `resources/read` refuse it without contacting the member. A bundle with no curation serves exactly as before.
  ([#146](https://github.com/wingfold-ai/bundlemcp/pull/146))
- Curating a member prompt or resource tells the bundle's connected clients that the prompt or resource list changed.
  ([#146](https://github.com/wingfold-ai/bundlemcp/pull/146))
- Each discovery probe of a member that advertises prompts or resources makes one or two more requests. The cache fills
  on each server's next discovery. ([#146](https://github.com/wingfold-ai/bundlemcp/pull/146))

### Fixed

- Hiding a member's resource no longer exposes another member's resource with the same URI in that bundle.
  ([#146](https://github.com/wingfold-ai/bundlemcp/pull/146))

## [0.1.12] - 2026-10-16

### Added

- Export the whole configuration with `GET /api/v1/export`: upstreams, bundles (members, enable flags, tool curation,
  prompts, resources) and endpoints, by name. The document is also a valid bootstrap file.
  ([#145](https://github.com/wingfold-ai/bundlemcp/pull/145))
- Import a configuration document with `POST /api/v1/import`, with an optional `dry_run=true`. It applies the document
  as upserts in one transaction and reports `created`, `updated`, `skipped` or `error` per resource. Any error rolls
  everything back, and an import never deletes anything. ([#145](https://github.com/wingfold-ai/bundlemcp/pull/145))
- Export header values and OAuth client secrets as `{"$secret": "<name>"}` placeholders. On import a placeholder keeps
  the stored value, and a placeholder with nothing stored is an error. Bootstrap files accept placeholders and the
  member object form (`enabled` plus per-tool curation) too. ([#145](https://github.com/wingfold-ai/bundlemcp/pull/145))
- Export secret values with `include_secrets=true`. This needs an admin session, since a service key gets 403. The
  response carries a `warning` field, and an audit record is written.
  ([#145](https://github.com/wingfold-ai/bundlemcp/pull/145))
- Rename a bundle with `POST /api/v1/bundles/{name}:rename?new_name=&force=`. The bundle keeps its members, curation,
  prompts, resources and endpoints. Without `force=true` it answers 409, because a document still naming the old bundle
  would create a new one. The bundle page has a rename card with that warning and an acknowledgement.
  ([#145](https://github.com/wingfold-ai/bundlemcp/pull/145))
- Add an Export and import card to Settings in the admin UI. It downloads an export, shows a dry-run report for a chosen
  file, and writes only after you click Apply import. ([#145](https://github.com/wingfold-ai/bundlemcp/pull/145))
- Record management actions in the audit log. Audit records now have a `kind` (`tool_call` or `management`) and an
  `action`, such as `export.secrets_included`. The audit list can be filtered by kind, the audit page shows the action,
  and the CSV export includes both columns. ([#145](https://github.com/wingfold-ai/bundlemcp/pull/145))

### Changed

- Bootstrap now applies its document through the same code as import, so the two behave identically. Existing bootstrap
  files stay valid. ([#145](https://github.com/wingfold-ai/bundlemcp/pull/145))
- Curation of a tool that has not been discovered yet is reported as `skipped` with "re-import after discovery" instead
  of failing. Import the same document again once discovery has run.
  ([#145](https://github.com/wingfold-ai/bundlemcp/pull/145))

### Security

- Refuse secret-bearing exports for service API keys. Only an admin session can export secret values, and each such
  export is written to the audit log without the values. ([#145](https://github.com/wingfold-ai/bundlemcp/pull/145))
- Never include users, OAuth server state, API keys, audit records or upstream tokens in an export. An import refuses a
  document carrying `api_keys`, since keys come only from bootstrap.
  ([#145](https://github.com/wingfold-ai/bundlemcp/pull/145))

## [0.1.11] - 2026-10-16

### Added

- Provision API keys from the bootstrap document with a new `api_keys` list. Each entry names a key, its kind and, for
  an endpoint key, its endpoints by name, and takes its value from an environment variable (`value_from_env`) or
  generates it on first boot (`create_if_missing`). ([#144](https://github.com/wingfold-ai/bundlemcp/pull/144))
- A generated bootstrap key is written to the file named by `write_to`, created exclusively with mode `0600` and never
  overwritten. A file that already holds a key value is reused, and any other existing file fails the document.
  ([#144](https://github.com/wingfold-ai/bundlemcp/pull/144))
- A bootstrap key whose name already exists is never overwritten, re-scoped or re-activated. A scope that names an
  unknown endpoint rolls the whole document back. ([#144](https://github.com/wingfold-ai/bundlemcp/pull/144))

### Changed

- API key names are now unique, and creating a key under a name that is already taken answers 409. A script that created
  several keys under one name now gets 409 for the second. ([#144](https://github.com/wingfold-ai/bundlemcp/pull/144))
- A database migration renames existing keys that share a name to `<name>-<first 8 characters of the id>` before it adds
  the unique constraint. Key values and scopes are untouched. Its downgrade drops the constraint and keeps the new
  names. ([#144](https://github.com/wingfold-ai/bundlemcp/pull/144))

### Security

- Bootstrap API keys never put a key value in the document or in a log line. An unset or malformed `value_from_env`
  variable fails the document before anything is written, and the error names the variable, never the value.
  ([#144](https://github.com/wingfold-ai/bundlemcp/pull/144))

## [0.1.10] - 2026-10-16

### Added

- Cache admin UI queries and validate names from the schema ([#143](https://github.com/wingfold-ai/bundlemcp/pull/143))

## [0.1.9] - 2026-10-16

### Added

- Keep upstream MCP sessions open and reuse them across requests, so most calls skip the upstream's `initialize`.
  Sessions are shared between callers only for identity-free servers; otherwise each caller and set of forwarded headers
  gets its own. ([#142](https://github.com/wingfold-ai/bundlemcp/pull/142))
- Deliver what a member server says between calls: tool, prompt and resource list changes, resource updates and log
  messages now reach clients on their GET stream or `subscriptions/listen` stream. A list change announced to several
  replicas triggers one re-discovery. ([#142](https://github.com/wingfold-ai/bundlemcp/pull/142))
- Relay `logging/setLevel` to the members that advertise logging, and relay `resources/subscribe` and the new
  `resources/unsubscribe` to the owning member. `subscriptions/listen` now honours `resourceSubscriptions`.
  ([#142](https://github.com/wingfold-ai/bundlemcp/pull/142))
- Advertise member list changes and `resources.subscribe` in a bundle's capabilities.
  ([#142](https://github.com/wingfold-ai/bundlemcp/pull/142))
- Add the `upstream_sessions_max`, `upstream_sessions_per_server_max` and `upstream_session_idle_timeout` runtime
  settings to cap and expire pooled upstream sessions, and `BUNDLEMCP_UPSTREAM_POOLING_ENABLED` to switch pooling off.
  With it set to `false`, every request opens its own upstream connection again.
  ([#142](https://github.com/wingfold-ai/bundlemcp/pull/142))

### Changed

- A handshake session's first call to a member opens an upstream session dedicated to it, and any replica continues that
  session without a new `initialize`. The upstream session ends when the client sends `DELETE` on the endpoint or the
  session expires. ([#142](https://github.com/wingfold-ai/bundlemcp/pull/142))
- Changing a server's URL, headers or authentication closes its pooled upstream sessions on every replica, and a replica
  that missed an event closes them all. The next call uses the new configuration.
  ([#142](https://github.com/wingfold-ai/bundlemcp/pull/142))
- At a session cap, the least recently used idle session is closed, identity-free ones first. When none can be closed,
  the request gets a connection of its own. ([#142](https://github.com/wingfold-ai/bundlemcp/pull/142))

### Fixed

- An upstream restart no longer shows up as a client error: the call is retried once on a new upstream session under the
  same idempotency key, so metering sees one `pre_call` and one `post_call`. A `tools/call` is retried only when the
  upstream cannot have run it; reads are also retried after any connection loss.
  ([#142](https://github.com/wingfold-ai/bundlemcp/pull/142))
- Resource subscriptions now deliver updates, and they are re-subscribed when a session is rebound to a new upstream
  session. ([#142](https://github.com/wingfold-ai/bundlemcp/pull/142))

## [0.1.8] - 2026-10-16

### Added

- Audit records carry the metering idempotency key of the invocation, the same on every leg of a paused and resumed
  call. `GET /api/v1/audit-records` filters by `idempotency_key`, so a metering ledger can reconcile by key instead of
  by time. ([#141](https://github.com/wingfold-ai/bundlemcp/pull/141))
- `GET /api/v1/audit-records:export` streams the whole filtered result as CSV, including the caller and idempotency key
  columns. It takes the same filters as the list and needs management credentials.
  ([#141](https://github.com/wingfold-ai/bundlemcp/pull/141))
- The audit page filters by bundle, upstream, API key and user, and shows how many records match.
  ([#141](https://github.com/wingfold-ai/bundlemcp/pull/141))
- A `tools/call` made with a valid credential that is not entitled to the endpoint is audited as `denied` with reason
  `forbidden`. The response is unchanged, and listings and authentication failures are still not audited.
  ([#141](https://github.com/wingfold-ai/bundlemcp/pull/141))
- A purge job deletes audit records older than `audit_retention_days` (90 by default). It runs every 15 minutes on one
  replica at a time, picks up setting changes without a restart, and `0` keeps everything.
  ([#141](https://github.com/wingfold-ai/bundlemcp/pull/141))
- Every audit record that is never written is logged with its idempotency key (`audit.queue_overflow`,
  `audit.write_failed` or `audit.lost_on_shutdown`) and counted in the new `bundlemcp_audit_dropped_total` metric,
  labelled by reason. ([#141](https://github.com/wingfold-ai/bundlemcp/pull/141))

### Changed

- Audit records are written in batches of up to 100. A failed write is retried with backoff for 60 seconds before it is
  given up, and shutdown drains the queue for up to 10 seconds.
  ([#141](https://github.com/wingfold-ai/bundlemcp/pull/141))
- Export CSV on the audit page downloads every record matching the current filters from the gateway, not only the loaded
  rows. ([#141](https://github.com/wingfold-ai/bundlemcp/pull/141))
- `audit_retention_days` now takes effect, and purging starts at the default of 90 days after upgrading. Set it to `0`
  before upgrading to keep every record. ([#141](https://github.com/wingfold-ai/bundlemcp/pull/141))
- The `0012` database migration adds a nullable, indexed `idempotency_key` column to the audit table. It only adds to
  the schema, so it is safe for the previous release. ([#141](https://github.com/wingfold-ai/bundlemcp/pull/141))

### Fixed

- A batch of audit records still being retried when the shutdown drain ran out is now logged as lost instead of being
  dropped silently. ([#141](https://github.com/wingfold-ai/bundlemcp/pull/141))

## [0.1.7] - 2026-10-16

### Added

- Serve Prometheus metrics at `/metrics` from every replica, readable with a service API key or an admin session (no
  credential gets 401, an endpoint key gets 403). Metrics cover tool calls and their duration, upstream in-flight calls
  and failures, rate-limit rejections, metering denials, auth failures and lockouts, open streams, audit queue depth,
  and Postgres and Valkey health. ([#140](https://github.com/wingfold-ai/bundlemcp/pull/140))
- Add `BUNDLEMCP_METRICS_ENABLED` (default `true`); setting it to `false` removes the `/metrics` route.
  ([#140](https://github.com/wingfold-ai/bundlemcp/pull/140))
- Count each `tools/list` that includes an unhealthy upstream's cached tools in `bundlemcp_tools_list_degraded_total`,
  per endpoint and server, and log a `tools_list.degraded` warning.
  ([#140](https://github.com/wingfold-ai/bundlemcp/pull/140))
- Add `bundlemcp_auth_limiter_fail_open_total`, so a Valkey outage that stops auth-failure limiting can be alerted on
  separately from the traffic limiter's `bundlemcp_traffic_limiter_fail_open_total`, with its own warning log.
  ([#140](https://github.com/wingfold-ai/bundlemcp/pull/140))

### Fixed

- The auth-failure limiter and the traffic rate limiter no longer raise the same fail-open counter, so a fail-open of
  one can be told apart from the other. ([#140](https://github.com/wingfold-ai/bundlemcp/pull/140))

### Security

- Metric labels are limited to endpoint and server names or fixed values, so no caller identity, API key, bearer token,
  header value, tool argument or client IP can appear in `/metrics`.
  ([#140](https://github.com/wingfold-ai/bundlemcp/pull/140))

## [0.1.6] - 2026-10-16

### Added

- Trace requests and report readiness check by check ([#139](https://github.com/wingfold-ai/bundlemcp/pull/139))

## [0.1.5] - 2026-10-16

### Added

- Expire idle sessions and drain stopping replicas in time ([#138](https://github.com/wingfold-ai/bundlemcp/pull/138))

## [0.1.4] - 2026-10-16

### Added

- Count live calls and every replica toward upstream health ([#137](https://github.com/wingfold-ai/bundlemcp/pull/137))

## [0.1.3] - 2026-10-16

### Fixed

- A pull request whose description contains a CI-skip marker (`[skip ci]`, `[ci skip]`, `[no ci]`, `[skip actions]`,
  `[actions skip]` or `skip-checks: true`) now fails its title check, so the squash merge can no longer carry the marker
  to `main` and skip CI, the image publish and the release. ([#136](https://github.com/wingfold-ai/bundlemcp/pull/136))

## [0.1.2] - 2026-10-16

### Changed

- The `ci-passed` result on CI's own `[skip ci]` commits (the changelog entry and the merge of `main`) is now set by the
  pull request branch's own CI run. The separate `ci-result-relay.yml` workflow is removed.
  ([#135](https://github.com/wingfold-ai/bundlemcp/pull/135))

### Fixed

- A pull request no longer stays pending on the required `ci-passed` check after CI pushes its own commit, so it no
  longer needs the result relayed by hand. A result for an older commit is never set on a newer head.
  ([#135](https://github.com/wingfold-ai/bundlemcp/pull/135))

## [0.1.1] - 2026-10-15

### Added

- Every merge into `main` that adds, fixes or improves something is now a release: its version follows from the pull
  request title, and the merge tags it and publishes the versioned images and the GitHub release without anyone pushing
  a tag. ([#134](https://github.com/wingfold-ai/bundlemcp/pull/134))

### Changed

- Changelog entries name the metering-hook protocol only in a release that changes it, as a breaking bullet; the
  `Metering-hook protocol: <n>` line is gone from entries. The GitHub release notes still end with the protocol version
  and whether it changed. ([#134](https://github.com/wingfold-ai/bundlemcp/pull/134))
- The gateway's reported version (OpenAPI `info.version` and MCP `serverInfo.version`) is read from the installed
  package, so it always matches the release. ([#134](https://github.com/wingfold-ai/bundlemcp/pull/134))

## [0.1.0] - 2026-10-15

The first release. It is the whole history from the repository's start on 2026-07-04 to this tag, grouped by what a
user, operator or integrator gets; pull requests are linked where the work landed through one. Releases from here on
list only what changed since the one before.

### Added

#### Bundling core

- Register upstream MCP servers over Streamable HTTP, compose them into bundles and expose each bundle through one or
  more endpoints, with Postgres for durable state and Valkey for live state, so any replica serves any session and a
  restart is a non-event ([#2](https://github.com/wingfold-ai/bundlemcp/pull/2)).
- Discover each upstream's tools into a cache, so bundles can be curated while an upstream is down, and refresh every
  upstream's tools on a schedule ([#56](https://github.com/wingfold-ai/bundlemcp/pull/56)).
- Guided upstream setup: check a URL, learn which authentication it needs, register it
  ([#57](https://github.com/wingfold-ai/bundlemcp/pull/57)).
- Leave idle upstreams alone: the gateway contacts an upstream only when it has a reason to
  ([#97](https://github.com/wingfold-ai/bundlemcp/pull/97)).
- Per-bundle tool curation: enable or disable a tool, override its name, title, description and annotations; a tool its
  upstream stops listing is flagged stale, no longer served, and can be pruned
  ([#109](https://github.com/wingfold-ai/bundlemcp/pull/109)).
- Prompts and resources owned by a bundle, served by the gateway without contacting any upstream
  ([#99](https://github.com/wingfold-ai/bundlemcp/pull/99), [#105](https://github.com/wingfold-ai/bundlemcp/pull/105)).
- A bundle refuses the gateway's own endpoints as members ([#123](https://github.com/wingfold-ai/bundlemcp/pull/123)).

#### Endpoints and profiles

- Endpoint profiles as registered presets: `default`, `oauth_only` and `write_as_read` (which re-annotates write tools
  as read-safe for clients that refuse them) ([#107](https://github.com/wingfold-ai/bundlemcp/pull/107),
  [#115](https://github.com/wingfold-ai/bundlemcp/pull/115)).
- Per-endpoint `allowed_origins`: which browser origins may use an endpoint, checked before authentication; an open
  endpoint refuses cross-site browsers by default ([#122](https://github.com/wingfold-ai/bundlemcp/pull/122)).
- Renaming an endpoint shows the old and new URL and what breaks, and is allowed only after the admin acknowledges it
  ([#128](https://github.com/wingfold-ai/bundlemcp/pull/128)).

#### MCP protocol

- A full bidirectional proxy: progress, cancellation, sampling, elicitation, roots and logging relayed between client
  and upstream, across replicas ([#2](https://github.com/wingfold-ai/bundlemcp/pull/2)).
- MCP 2026-07-28 served beside the handshake-era revisions (2025-03-26 to 2025-11-25) through one dialect per revision,
  with the revision and method tables read from the MCP SDK ([#20](https://github.com/wingfold-ai/bundlemcp/pull/20),
  [#21](https://github.com/wingfold-ai/bundlemcp/pull/21), [#27](https://github.com/wingfold-ai/bundlemcp/pull/27)).
- Multi Round-Trip Requests: a modern client is asked for input as `input_required` and continues on any replica, for
  `tools/call`, `prompts/get` and `resources/read` ([#21](https://github.com/wingfold-ai/bundlemcp/pull/21),
  [#127](https://github.com/wingfold-ai/bundlemcp/pull/127)).
- Cancellation for modern clients by request id from the same caller, and on a client disconnect from a buffered call
  ([#130](https://github.com/wingfold-ai/bundlemcp/pull/130)).
- The MCP conformance suite runs through the gateway in CI for every served revision it covers
  ([#130](https://github.com/wingfold-ai/bundlemcp/pull/130)).

#### Authentication and OAuth

- An OAuth 2.1 authorization server toward MCP clients: dynamic client registration, PKCE, consent, refresh and
  revocation, audience-bound tokens, issuer identification, Client ID Metadata Documents and `application_type`
  ([#2](https://github.com/wingfold-ai/bundlemcp/pull/2), [#22](https://github.com/wingfold-ai/bundlemcp/pull/22),
  [#125](https://github.com/wingfold-ai/bundlemcp/pull/125)).
- A configurable redirect-URI allow-list and limits for dynamic client registration
  ([#80](https://github.com/wingfold-ai/bundlemcp/pull/80)).
- People can see and withdraw the clients they authorised ([#125](https://github.com/wingfold-ai/bundlemcp/pull/125)).
- API keys for scripts and service keys for the management API ([#2](https://github.com/wingfold-ai/bundlemcp/pull/2)).
- Admin sign-in through any OIDC provider, with PKCE; admin rights by email list or by a configurable claim; a
  configurable session lifetime; deactivating a user sticks until an admin reactivates them
  ([#2](https://github.com/wingfold-ai/bundlemcp/pull/2), [#82](https://github.com/wingfold-ai/bundlemcp/pull/82),
  [#124](https://github.com/wingfold-ai/bundlemcp/pull/124)).
- Upstream OAuth: discover, register and connect OAuth-protected upstreams end to end, per user or shared, with
  delegated tokens for identity-aware upstreams and a connect-account tool for users who have not connected yet
  ([#51](https://github.com/wingfold-ai/bundlemcp/pull/51), [#57](https://github.com/wingfold-ai/bundlemcp/pull/57)).
- The identity provider's subject exposed to the metering hook and to token introspection
  ([#79](https://github.com/wingfold-ai/bundlemcp/pull/79)).

#### Metering

- A versioned metering hook around every tool call, in process or out of process over HTTP, reporting how each call
  ended (`result`, `tool_error`, `no_result`, `cancelled`) ([#2](https://github.com/wingfold-ai/bundlemcp/pull/2),
  [#90](https://github.com/wingfold-ai/bundlemcp/pull/90)).
- The hook is asked once per invocation, also across Multi Round-Trip legs, and an abandoned invocation is closed with
  `no_result`; its context carries the auth method, profile, session, credential-free headers and a scratch mapping
  ([#127](https://github.com/wingfold-ai/bundlemcp/pull/127)).

#### Operations

- Per-endpoint and per-client rate limits, and a per-IP lockout on bad credentials
  ([#2](https://github.com/wingfold-ai/bundlemcp/pull/2)).
- An audit log of every tool call ([#2](https://github.com/wingfold-ai/bundlemcp/pull/2)).
- Re-encryption of stored secrets after an encryption-key rotation
  ([#126](https://github.com/wingfold-ai/bundlemcp/pull/126)).
- A request body limit and an upstream response cap, both changeable at runtime
  ([#121](https://github.com/wingfold-ai/bundlemcp/pull/121)).
- A declarative bootstrap document (YAML or JSON, inline or from a file) applied at startup
  ([#32](https://github.com/wingfold-ai/bundlemcp/pull/32)).
- A one-command dev stack behind a tunnel, with an OAuth-protected demo upstream
  ([#100](https://github.com/wingfold-ai/bundlemcp/pull/100)).
- Images for the gateway and the web app published to GHCR ([#49](https://github.com/wingfold-ai/bundlemcp/pull/49));
  tagged releases with notes from this changelog, after a restore rehearsal against the compose stack
  ([#129](https://github.com/wingfold-ai/bundlemcp/pull/129)).

#### Admin UI and documentation

- An admin UI (Nuxt) for upstreams, bundles, endpoints, users, keys and runtime settings, and a catalogue for signed-in
  non-admins ([#2](https://github.com/wingfold-ai/bundlemcp/pull/2),
  [#58](https://github.com/wingfold-ai/bundlemcp/pull/58)).
- A documentation site for operators and integrators, with quickstart, setup guide, concepts and auth flow diagrams
  ([#38](https://github.com/wingfold-ai/bundlemcp/pull/38), [#45](https://github.com/wingfold-ai/bundlemcp/pull/45),
  [#92](https://github.com/wingfold-ai/bundlemcp/pull/92), [#101](https://github.com/wingfold-ai/bundlemcp/pull/101),
  [#110](https://github.com/wingfold-ai/bundlemcp/pull/110)).

### Changed

These changed before the first release; they matter only to someone who ran a pre-release build.

- The management API, documents and UI say "upstreams" instead of "servers"
  ([#98](https://github.com/wingfold-ai/bundlemcp/pull/98)).
- Endpoint profiles are named for what they change: `claude` became `oauth_only`, `chatgpt` became `write_as_read`
  ([#115](https://github.com/wingfold-ai/bundlemcp/pull/115)).
- Metering protocol version 2: `post_call` reports an outcome instead of `success` or `error`
  ([#90](https://github.com/wingfold-ai/bundlemcp/pull/90)).
- MCP endpoints answer CORS only for an endpoint's allowed origins
  ([#122](https://github.com/wingfold-ai/bundlemcp/pull/122)).
- A signed-in non-admin gets 403 from the management API ([#124](https://github.com/wingfold-ai/bundlemcp/pull/124)).
- The upstream MCP client moved to FastMCP 4 ([#20](https://github.com/wingfold-ai/bundlemcp/pull/20)); the stack runs
  on Python 3.14 ([#117](https://github.com/wingfold-ai/bundlemcp/pull/117)) and the web image on Node 26
  ([#74](https://github.com/wingfold-ai/bundlemcp/pull/74)), with Node 24 or later required to build the web app
  ([#129](https://github.com/wingfold-ai/bundlemcp/pull/129)).

### Fixed

- Sessions are served and ended only for the caller who opened them
  ([#76](https://github.com/wingfold-ai/bundlemcp/pull/76)).
- The gateway reconnects to Valkey after a restart instead of answering 500
  ([#87](https://github.com/wingfold-ai/bundlemcp/pull/87)), and retries OIDC discovery instead of disabling login until
  a restart ([#88](https://github.com/wingfold-ai/bundlemcp/pull/88)).
- ID tokens are verified with joserfc, with issuer and audience validated
  ([#23](https://github.com/wingfold-ai/bundlemcp/pull/23)).
- Upstream OAuth requests the scopes the protected resource asks for
  ([#52](https://github.com/wingfold-ai/bundlemcp/pull/52), [#53](https://github.com/wingfold-ai/bundlemcp/pull/53));
  client metadata documents that list grants the gateway does not issue are accepted
  ([#50](https://github.com/wingfold-ai/bundlemcp/pull/50)).
- The consent page's CSP allows the validated redirect URI ([#84](https://github.com/wingfold-ai/bundlemcp/pull/84)).
- Migration 0001 is a frozen schema, not `create_all` ([#30](https://github.com/wingfold-ai/bundlemcp/pull/30)).
- The admin UI stays inside the window and its tables are readable
  ([#58](https://github.com/wingfold-ai/bundlemcp/pull/58)).
- Flaky tests made deterministic ([#9](https://github.com/wingfold-ai/bundlemcp/pull/9),
  [#10](https://github.com/wingfold-ai/bundlemcp/pull/10)).

### Security

- The HTTP edge is hardened: the client IP is taken from the right of `X-Forwarded-For` and only from trusted proxies,
  forwarded protocol and host are ignored, and the egress policy is enforced where each connection is dialled, which
  closes DNS rebinding ([#121](https://github.com/wingfold-ai/bundlemcp/pull/121)).
- The authorization server and the upstream client are hardened
  ([#24](https://github.com/wingfold-ai/bundlemcp/pull/24)); token revocation requires client authentication
  ([#31](https://github.com/wingfold-ai/bundlemcp/pull/31)).
- An upstream's tokens are deleted when its user is deactivated
  ([#124](https://github.com/wingfold-ai/bundlemcp/pull/124)).

### Internal

- Four clean-architecture layers with application-owned contracts, Pydantic entities, a unit of work and import
  contracts enforced in CI ([#7](https://github.com/wingfold-ai/bundlemcp/pull/7),
  [#8](https://github.com/wingfold-ai/bundlemcp/pull/8), [#11](https://github.com/wingfold-ai/bundlemcp/pull/11),
  [#13](https://github.com/wingfold-ai/bundlemcp/pull/13), [#14](https://github.com/wingfold-ai/bundlemcp/pull/14),
  [#35](https://github.com/wingfold-ai/bundlemcp/pull/35), [#37](https://github.com/wingfold-ai/bundlemcp/pull/37)).
- Controllers for every HTTP surface; the MCP edge decomposed into routing, protocol adapters, a method registry and a
  tool-call object ([#4](https://github.com/wingfold-ai/bundlemcp/pull/4),
  [#5](https://github.com/wingfold-ai/bundlemcp/pull/5), [#6](https://github.com/wingfold-ai/bundlemcp/pull/6),
  [#12](https://github.com/wingfold-ai/bundlemcp/pull/12), [#16](https://github.com/wingfold-ai/bundlemcp/pull/16),
  [#18](https://github.com/wingfold-ai/bundlemcp/pull/18), [#19](https://github.com/wingfold-ai/bundlemcp/pull/19),
  [#44](https://github.com/wingfold-ai/bundlemcp/pull/44), [#47](https://github.com/wingfold-ai/bundlemcp/pull/47)).
- Specifications moved to OpenSpec, with documentation drift checked in CI
  ([#48](https://github.com/wingfold-ai/bundlemcp/pull/48), [#99](https://github.com/wingfold-ai/bundlemcp/pull/99),
  [#106](https://github.com/wingfold-ai/bundlemcp/pull/106), [#108](https://github.com/wingfold-ai/bundlemcp/pull/108)).
- Repository prepared for contributors; dependencies kept current
  ([#3](https://github.com/wingfold-ai/bundlemcp/pull/3), [#25](https://github.com/wingfold-ai/bundlemcp/pull/25),
  [#26](https://github.com/wingfold-ai/bundlemcp/pull/26), [#28](https://github.com/wingfold-ai/bundlemcp/pull/28),
  [#29](https://github.com/wingfold-ai/bundlemcp/pull/29), [#33](https://github.com/wingfold-ai/bundlemcp/pull/33),
  [#55](https://github.com/wingfold-ai/bundlemcp/pull/55), [#59](https://github.com/wingfold-ai/bundlemcp/pull/59),
  [#60](https://github.com/wingfold-ai/bundlemcp/pull/60), [#61](https://github.com/wingfold-ai/bundlemcp/pull/61),
  [#62](https://github.com/wingfold-ai/bundlemcp/pull/62), [#63](https://github.com/wingfold-ai/bundlemcp/pull/63),
  [#64](https://github.com/wingfold-ai/bundlemcp/pull/64), [#65](https://github.com/wingfold-ai/bundlemcp/pull/65),
  [#66](https://github.com/wingfold-ai/bundlemcp/pull/66), [#67](https://github.com/wingfold-ai/bundlemcp/pull/67),
  [#68](https://github.com/wingfold-ai/bundlemcp/pull/68), [#70](https://github.com/wingfold-ai/bundlemcp/pull/70),
  [#73](https://github.com/wingfold-ai/bundlemcp/pull/73), [#75](https://github.com/wingfold-ai/bundlemcp/pull/75),
  [#91](https://github.com/wingfold-ai/bundlemcp/pull/91), [#96](https://github.com/wingfold-ai/bundlemcp/pull/96),
  [#102](https://github.com/wingfold-ai/bundlemcp/pull/102), [#103](https://github.com/wingfold-ai/bundlemcp/pull/103),
  [#116](https://github.com/wingfold-ai/bundlemcp/pull/116)).

## Before 0.1.0

Every pull request merged into `main` before the first release, newest first. None of them was released on its own:
each was unreleased until it shipped in 0.1.0, so this section is history, not a list of versions.

### docs(repo): Write the changelog for 0.1.0 ([#131](https://github.com/wingfold-ai/bundlemcp/pull/131)) — 2026-10-15

Wrote the 0.1.0 entry of this changelog.

### feat(gateway): Complete cancellation, capabilities and MCP conformance ([#130](https://github.com/wingfold-ai/bundlemcp/pull/130)) — 2026-10-15

A modern client cancels its own in-flight call by request id, from any replica; disconnecting from a buffered call
cancels it. Members' `listChanged` and `resources.subscribe` are no longer advertised, a `tools/list` with a caller's
connect-account tool is `cacheScope: private`, and CI runs the MCP conformance suite through the gateway per served
revision.

### feat(deploy): Cut tagged releases with notes from the changelog ([#129](https://github.com/wingfold-ai/bundlemcp/pull/129)) — 2026-10-15

Tagged `v<semver>` releases: changelog check, restore rehearsal, images as `:<version>`, and a GitHub release naming the
metering-hook protocol version. CI typechecks the web app, and every job runs Node 24 or later.

### feat(endpoints): State a rename's consequence before allowing it ([#128](https://github.com/wingfold-ai/bundlemcp/pull/128)) — 2026-10-15

The endpoint rename shows the old and new URL and what breaks, and is enabled only after the admin acknowledges it. An
unsupported upstream `transport` answers a 422 that names the one supported value.

### feat(gateway): Meter each tool invocation once, through one stage chain ([#127](https://github.com/wingfold-ai/bundlemcp/pull/127)) — 2026-10-15

Tools pass one ordered stage chain (filter, profile, overrides, metering, audit). The metering hook is asked once per
invocation, also across Multi Round-Trip legs; an abandoned invocation gets `post_call` `no_result`. The hook context
gains auth method, profile, session, credential-free headers and a `scratch` mapping. `prompts/get` and `resources/read`
can ask a modern client for input.

### feat(deploy): Re-encrypt stored secrets after a key rotation ([#126](https://github.com/wingfold-ai/bundlemcp/pull/126)) — 2026-10-15

A background sweep moves stored upstream tokens and client secrets under the primary encryption key after a rotation, so
an old key can be dropped once nothing needs it (`BUNDLEMCP_TOKEN_REENCRYPTION_INTERVAL`).

### feat(auth): Complete the OAuth server toward MCP clients ([#125](https://github.com/wingfold-ai/bundlemcp/pull/125)) — 2026-10-15

The OAuth server toward MCP clients: an `invalid_token` challenge for a refused bearer, `resource` honoured at the token
endpoint, users can list and withdraw their own consents, and the end-to-end test makes a tool call.

### feat(auth)!: Make deactivation stick and admin rights configurable ([#124](https://github.com/wingfold-ai/bundlemcp/pull/124)) — 2026-10-15

**Breaking:** a non-admin session gets 403 from the management API. Deactivating a user deletes their upstream tokens
and sticks until an admin reactivates them; admin rights can come from an IdP claim, and the admin session lifetime is
configurable.

### feat(bundles): Refuse the gateway's own endpoints as bundle members ([#123](https://github.com/wingfold-ai/bundlemcp/pull/123)) — 2026-10-15

A bundle refuses one of the gateway's own MCP endpoints as a member, which would make tool calls re-enter the gateway.

### feat(endpoints)!: Let each endpoint list the browser origins that may use it ([#122](https://github.com/wingfold-ai/bundlemcp/pull/122)) — 2026-10-15

**Breaking:** each endpoint lists the browser origins that may use it (`allowed_origins`), checked before
authentication; open endpoints refuse cross-site browsers by default.

### fix(security): Harden the HTTP edge ([#121](https://github.com/wingfold-ai/bundlemcp/pull/121)) — 2026-10-15

Security hardening of the HTTP edge: rightmost trusted `X-Forwarded-For`, forwarded protocol and host ignored, egress
policy enforced at connect time against DNS rebinding, a request body limit and an upstream response cap.

### build(deps): Update Python libraries, the web icon set and GitHub Actions ([#116](https://github.com/wingfold-ai/bundlemcp/pull/116)) — 2026-10-15

Dependency updates: Python libraries, the web icon set and GitHub Actions.

### build(deploy): Build, test and ship on Python 3.14 ([#117](https://github.com/wingfold-ai/bundlemcp/pull/117)) — 2026-10-15

Build, test and ship on Python 3.14, declared once and checked across images and CI.

### feat(bundles): Stop serving vanished tools and complete tool curation ([#109](https://github.com/wingfold-ai/bundlemcp/pull/109)) — 2026-10-15

A tool its upstream stops listing is flagged stale and no longer served, and can be pruned; tool curation is complete
(title, description and annotation overrides, inline edits).

### feat(endpoints)!: Name endpoint profiles for what they change ([#115](https://github.com/wingfold-ai/bundlemcp/pull/115)) — 2026-10-15

**Breaking:** endpoint profiles are named for what they change: `claude` becomes `oauth_only`, `chatgpt` becomes
`write_as_read` (migration included).

### docs(repo): Clarify the guides and make the configuration page the reference ([#110](https://github.com/wingfold-ai/bundlemcp/pull/110)) — 2026-10-14

Clearer guides; the configuration page is the reference for every environment variable.

### docs(repo): Correct documentation that describes unbuilt behaviour ([#108](https://github.com/wingfold-ai/bundlemcp/pull/108)) — 2026-10-13

Documentation corrected where it described behaviour that was not built yet.

### feat(endpoints): Make each profile one registered preset ([#107](https://github.com/wingfold-ai/bundlemcp/pull/107)) — 2026-10-13

Each endpoint profile is one registered preset, and the served tool set is built by ordered stages.

### docs(spec): Move the specifications to OpenSpec ([#106](https://github.com/wingfold-ai/bundlemcp/pull/106)) — 2026-10-13

Specifications moved to OpenSpec: every new behaviour starts as a change proposal.

### feat(bundles): Serve prompts and resources owned by a bundle ([#105](https://github.com/wingfold-ai/bundlemcp/pull/105)) — 2026-10-13

Bundles serve prompts and resources of their own, without contacting any upstream, editable in the admin UI.

### docs(spec): Add prompts and resources owned by a bundle ([#99](https://github.com/wingfold-ai/bundlemcp/pull/99)) — 2026-10-13

Specification for prompts and resources owned by a bundle.

### chore(deploy): Ignore the local compose override file ([#103](https://github.com/wingfold-ai/bundlemcp/pull/103)) — 2026-10-13

The local compose override file is ignored.

### test(web): Run the UI suite against the demo seed ([#102](https://github.com/wingfold-ai/bundlemcp/pull/102)) — 2026-10-12

The UI test suite runs against the demo seed.

### feat(api)!: Rename servers to upstreams ([#98](https://github.com/wingfold-ai/bundlemcp/pull/98)) — 2026-10-12

**Breaking:** "servers" are "upstreams" across the management API, bootstrap documents, the admin UI and the docs.

### docs(guide): UI-first quickstart, setup guide, and concepts for MCP newcomers ([#101](https://github.com/wingfold-ai/bundlemcp/pull/101)) — 2026-10-12

A UI-first quickstart, a setup guide and concepts for MCP newcomers.

### feat(stack): One-command dev stack behind a tunnel, with an OAuth-protected demo upstream ([#100](https://github.com/wingfold-ai/bundlemcp/pull/100)) — 2026-10-12

A one-command dev stack behind a tunnel (`deploy/stack.sh`), with an OAuth-protected demo upstream.

### feat(gateway): Leave idle upstreams alone outside tool calls ([#97](https://github.com/wingfold-ai/bundlemcp/pull/97)) — 2026-10-12

The gateway leaves idle upstreams alone: an update probes only when a discovery input changed, and nothing else wakes a
scaled-to-zero upstream outside tool calls.

### fix(docs): Point repository links at wingfold-ai/bundlemcp ([#96](https://github.com/wingfold-ai/bundlemcp/pull/96)) — 2026-10-12

Repository links point at wingfold-ai/bundlemcp.

### feat(docs): Add auth flow diagrams, Plausible analytics and a password gate ([#92](https://github.com/wingfold-ai/bundlemcp/pull/92)) — 2026-10-09

Authentication flow diagrams, Plausible analytics and an optional password gate for the documentation site.

### ci(docs): Publish the documentation site to Infomaniak web hosting ([#91](https://github.com/wingfold-ai/bundlemcp/pull/91)) — 2026-10-09

The documentation site is published to Infomaniak web hosting, with a size check on every pull request.

### feat(api)!: Let the metering hook also run out of process over HTTP ([#90](https://github.com/wingfold-ai/bundlemcp/pull/90)) — 2026-10-08

**Breaking:** the metering hook can run out of process over HTTP. Protocol version 2: `post_call` reports an outcome
(`result`, `tool_error`, `no_result`, `cancelled`), an unanswered `pre_call` is followed up, and a denial can carry a
message for the person.

### fix(auth): Retry OIDC discovery instead of disabling login until restart ([#88](https://github.com/wingfold-ai/bundlemcp/pull/88)) — 2026-10-08

OIDC discovery is retried instead of disabling login until a restart.

### fix(core): Reconnect to Valkey after a restart instead of answering 500 ([#87](https://github.com/wingfold-ai/bundlemcp/pull/87)) — 2026-10-08

The gateway reconnects to Valkey after a restart instead of answering 500.

### fix(oauth): Allow the validated redirect URI in the consent page's CSP form-action ([#84](https://github.com/wingfold-ai/bundlemcp/pull/84)) — 2026-10-08

The consent page's CSP allows the validated redirect URI, so Approve and Deny reach clients on another origin.

### fix(auth): Send PKCE (S256) on the gateway's login to the OIDC provider ([#82](https://github.com/wingfold-ai/bundlemcp/pull/82)) — 2026-10-08

The gateway's login to the OIDC provider sends PKCE (S256).

### feat(oauth): Make the DCR redirect-URI allow-list and limits configurable ([#80](https://github.com/wingfold-ai/bundlemcp/pull/80)) — 2026-10-08

A configurable redirect-URI allow-list and limits for dynamic client registration; bootstrap discovers tools for the
upstreams it creates.

### feat(auth): Expose the IdP subject to the metering hook and introspection ([#79](https://github.com/wingfold-ai/bundlemcp/pull/79)) — 2026-10-08

The identity provider's issuer and subject reach the metering hook and token introspection.

### fix(auth): Serve and end a session only for the caller who opened it ([#76](https://github.com/wingfold-ai/bundlemcp/pull/76)) — 2026-10-08

Security: a session is served and ended only for the caller who opened it; `DELETE` runs admission.

### chore(deps-dev): Bump typescript from 5.9.3 to 6.0.3 in /apps/web ([#75](https://github.com/wingfold-ai/bundlemcp/pull/75)) — 2026-10-08

TypeScript 6.0.3 in the web app.

### docs(repo): Correct documentation drift and gate it in CI ([#48](https://github.com/wingfold-ai/bundlemcp/pull/48)) — 2026-10-08

Documentation drift corrected after a five-reviewer audit, and the consistency checks gated in CI.

### fix(web): Keep the admin UI inside the window and make its tables readable ([#58](https://github.com/wingfold-ai/bundlemcp/pull/58)) — 2026-10-08

The admin UI stays inside the window and its tables are readable.

### chore(deps): Bump the minor-and-patch group with 11 updates ([#73](https://github.com/wingfold-ai/bundlemcp/pull/73)) — 2026-10-07

Dependency updates: the Python minor-and-patch group (11 updates).

### chore(deps): Update the web app dependencies and its image to Node 26 ([#74](https://github.com/wingfold-ai/bundlemcp/pull/74)) — 2026-10-07

Web app dependencies updated and its image moved to Node 26.

### chore(deps): Bump the actions group with 6 updates ([#70](https://github.com/wingfold-ai/bundlemcp/pull/70)) — 2026-10-07

GitHub Actions updated (6).

### chore(repo): Prepare the repository for open-source contributors ([#61](https://github.com/wingfold-ai/bundlemcp/pull/61)) — 2026-10-07

Apache-2.0 license, contributor guide, code of conduct, security policy and hardened workflows.

### chore(deps): Bump seroval from 1.5.4 to 1.6.8 in /apps/web ([#66](https://github.com/wingfold-ai/bundlemcp/pull/66)) — 2026-10-07

seroval 1.6.8 in the web app.

### fix(docs): Run the documentation site on Vite 6.4 ([#68](https://github.com/wingfold-ai/bundlemcp/pull/68)) — 2026-10-07

The documentation site runs on Vite 6.4, closing the vite and esbuild alerts.

### fix(web): Upgrade Nuxt to 4.6 and refresh the web dependencies ([#67](https://github.com/wingfold-ai/bundlemcp/pull/67)) — 2026-10-07

Nuxt 4.6 and refreshed web dependencies, closing 63 Dependabot alerts.

### chore(deps): Bump cryptography from 49.0.0 to 50.0.0 ([#65](https://github.com/wingfold-ai/bundlemcp/pull/65)) — 2026-10-07

cryptography 50.0.0.

### chore(deps): Bump shell-quote from 1.9.0 to 1.12.0 in /apps/web ([#64](https://github.com/wingfold-ai/bundlemcp/pull/64)) — 2026-10-07

shell-quote 1.12.0 in the web app.

### chore(deps): Bump anyio from 4.14.1 to 4.14.2 ([#62](https://github.com/wingfold-ai/bundlemcp/pull/62)) — 2026-10-07

anyio 4.14.2.

### chore(deps): Bump source-map-js from 1.2.1 to 1.2.2 in /docs ([#63](https://github.com/wingfold-ai/bundlemcp/pull/63)) — 2026-10-07

source-map-js 1.2.2 in the docs.

### chore(deps): Bump pyjwt from 2.13.0 to 2.15.0 ([#60](https://github.com/wingfold-ai/bundlemcp/pull/60)) — 2026-10-07

pyjwt 2.15.0.

### chore(deps): Bump mako from 1.3.12 to 1.4.2 ([#59](https://github.com/wingfold-ai/bundlemcp/pull/59)) — 2026-10-07

mako 1.4.2.

### feat(discovery): Refresh every server's tools on a schedule ([#56](https://github.com/wingfold-ai/bundlemcp/pull/56)) — 2026-09-30

Every upstream's tools are re-discovered on a schedule (`BUNDLEMCP_DISCOVERY_REFRESH_INTERVAL`), so an upstream
registered before it was running gets its tools.

### feat(servers): Guided server setup, spec-conformant upstream OAuth and delegated tokens ([#57](https://github.com/wingfold-ai/bundlemcp/pull/57)) — 2026-09-30

Guided upstream setup (check a URL, learn its authentication, register), spec-conformant upstream OAuth and delegated
tokens for identity-aware upstreams. Landed through [#56](https://github.com/wingfold-ai/bundlemcp/pull/56).

### chore(claude): Enable the software-architecture, git-conventions and docker plugins ([#55](https://github.com/wingfold-ai/bundlemcp/pull/55)) — 2026-09-24

Claude Code plugins for software architecture, git conventions and Docker.

### fix(upstream-oauth): Ask the resource for scopes a remembered client lacks ([#53](https://github.com/wingfold-ai/bundlemcp/pull/53)) — 2026-09-21

Upstream OAuth asks the resource for scopes a remembered client lacks.

### fix(upstream-oauth): Request the scopes the protected resource asks for ([#52](https://github.com/wingfold-ai/bundlemcp/pull/52)) — 2026-09-21

Upstream OAuth requests the scopes the protected resource asks for.

### feat(upstream-oauth): Discover, register and connect OAuth-protected upstreams end to end ([#51](https://github.com/wingfold-ai/bundlemcp/pull/51)) — 2026-09-21

OAuth-protected upstreams discovered, registered and connected end to end, with a connect-account tool for users who
have not connected yet.

### fix(oauth): Accept client metadata documents that list grants we do not issue ([#50](https://github.com/wingfold-ai/bundlemcp/pull/50)) — 2026-09-21

Client metadata documents that list grants the gateway does not issue are accepted (claude.ai).

### ci(images): Publish the gateway and web images to GHCR ([#49](https://github.com/wingfold-ai/bundlemcp/pull/49)) — 2026-09-21

The gateway and web images are published to GHCR as `:latest` and `:<sha>`.

### refactor(oauth): Restructure the OAuth authorization server slice ([#47](https://github.com/wingfold-ai/bundlemcp/pull/47)) — 2026-09-18

The OAuth authorization server slice restructured into resolution, consent and issuance, with clock, hasher and
generator as contracts.

### docs(authentication): One end-to-end authentication guide ([#45](https://github.com/wingfold-ai/bundlemcp/pull/45)) — 2026-09-17

One end-to-end authentication guide.

### refactor(mcp): Decompose the gateway into routing, protocol, dispatch and relay ([#44](https://github.com/wingfold-ai/bundlemcp/pull/44)) — 2026-09-15

The MCP edge decomposed into routing, protocol, dispatch and relay, with a front controller over two protocol adapters.

### docs(site): VitePress documentation site for operators and integrators ([#38](https://github.com/wingfold-ai/bundlemcp/pull/38)) — 2026-09-14

A VitePress documentation site for operators and integrators.

### refactor(architecture): Four clean-architecture layers with application-owned contracts and Pydantic entities ([#37](https://github.com/wingfold-ai/bundlemcp/pull/37)) — 2026-09-08

Four clean-architecture layers with application-owned contracts and Pydantic entities.

### refactor(services): Put every service on a UnitOfWork instead of a raw session ([#35](https://github.com/wingfold-ai/bundlemcp/pull/35)) — 2026-09-07

Every service sits on a UnitOfWork instead of a raw session.

### refactor(e2e): Drop the JavaScript twin of spec-map ([#33](https://github.com/wingfold-ai/bundlemcp/pull/33)) — 2026-09-06

The JavaScript twin of the E2E spec map is gone; the Node scripts import the TypeScript module.

### feat(bootstrap): Inline JSON document, a format version, and a real README ([#32](https://github.com/wingfold-ai/bundlemcp/pull/32)) — 2026-09-06

Bootstrap documents inline as JSON (`BUNDLEMCP_BOOTSTRAP`), with a format version and a README.

### fix(oauth): Revocation requires client authentication ([#31](https://github.com/wingfold-ai/bundlemcp/pull/31)) — 2026-09-06

Security: token revocation requires client authentication.

### fix(migrations): Make revision 0001 a frozen schema, not create_all ([#30](https://github.com/wingfold-ai/bundlemcp/pull/30)) — 2026-09-06

Migration 0001 is a frozen schema instead of `create_all`.

### refactor(web): One error decoder, a 401 middleware, useState identity, published name pattern ([#29](https://github.com/wingfold-ai/bundlemcp/pull/29)) — 2026-09-06

Admin UI: one error decoder, a 401 middleware, shared identity state and the published name pattern.

### chore(deploy): Build context, non-root images, health checks, compose profiles, frontend CI ([#28](https://github.com/wingfold-ai/bundlemcp/pull/28)) — 2026-09-06

Smaller, non-root images with health checks, compose profiles, and frontend CI.

### refactor(gateway): Read the revision and method tables from the SDK registry ([#27](https://github.com/wingfold-ai/bundlemcp/pull/27)) — 2026-09-06

Revision and method tables read from the MCP SDK registry.

### chore(test): One serving() harness instead of twelve copies of the app wiring ([#26](https://github.com/wingfold-ai/bundlemcp/pull/26)) — 2026-09-06

One `serving()` test harness instead of twelve copies of the app wiring.

### refactor(core): Remove dead code, parse at the boundary, dedupe the skeleton ([#25](https://github.com/wingfold-ai/bundlemcp/pull/25)) — 2026-09-06

Dead code removed, input parsed at the boundary, the skeleton deduplicated.

### fix(oauth): Harden the authorization server and the upstream client ([#24](https://github.com/wingfold-ai/bundlemcp/pull/24)) — 2026-09-06

Security hardening of the authorization server and the upstream OAuth client, including egress checks on every upstream
OAuth request.

### fix(oidc): Verify ID tokens with joserfc and validate issuer and audience ([#23](https://github.com/wingfold-ai/bundlemcp/pull/23)) — 2026-09-06

ID tokens verified with joserfc, with issuer and audience validated.

### feat(oauth): Send iss, accept Client ID Metadata Documents and validate the upstream issuer ([#22](https://github.com/wingfold-ai/bundlemcp/pull/22)) — 2026-09-06

`iss` on authorization responses, Client ID Metadata Documents, `application_type`, and upstream issuer validation.

### feat(gateway): Serve MCP 2026-07-28 beside the handshake era through one dialect per revision ([#21](https://github.com/wingfold-ai/bundlemcp/pull/21)) — 2026-09-05

MCP 2026-07-28 served beside the handshake revisions through one dialect per revision, converting between eras in both
directions, with Multi Round-Trip Requests.

### feat(gateway): Adopt MCP 2026-07-28 in the specs and move the upstream client to FastMCP 4 ([#20](https://github.com/wingfold-ai/bundlemcp/pull/20)) — 2026-09-05

Specifications adopt MCP 2026-07-28, and the upstream client moves to FastMCP 4.

### refactor(oauth): Move the authorization server into services with grant strategies ([#19](https://github.com/wingfold-ai/bundlemcp/pull/19)) — 2026-09-04

The OAuth authorization server moved into services with grant strategies.

### refactor(gateway): Dispatch the MCP edge through a method registry and make a tool call an object ([#16](https://github.com/wingfold-ai/bundlemcp/pull/16)) — 2026-09-04

The MCP edge dispatches through a method registry, and a tool call is an object.

### refactor(api): Declare the management API as controllers ([#18](https://github.com/wingfold-ai/bundlemcp/pull/18)) — 2026-09-03

The management API declared as controllers.

### refactor(core): Put services on a repository and unit of work behind one typed container ([#14](https://github.com/wingfold-ai/bundlemcp/pull/14)) — 2026-09-03

Services on a repository and unit of work behind one typed container.

### refactor(core): Replace tuples and dicts with value objects and give entities their rules ([#13](https://github.com/wingfold-ai/bundlemcp/pull/13)) — 2026-09-03

Value objects instead of tuples and dicts; entities carry their own rules.

### refactor(gateway): Decompose the 1113-line MCP edge ([#12](https://github.com/wingfold-ai/bundlemcp/pull/12)) — 2026-09-03

The 1113-line MCP edge module decomposed.

### refactor(core): Enforce layer direction with import contracts and name modules for what they hold ([#11](https://github.com/wingfold-ai/bundlemcp/pull/11)) — 2026-09-03

Layer direction enforced with import contracts; modules named for what they hold.

### fix(test): Freeze the fixture clock so fixed-window tests are deterministic ([#10](https://github.com/wingfold-ai/bundlemcp/pull/10)) — 2026-09-03

The fixture clock is frozen, so fixed-window tests are deterministic.

### refactor(core): Describe every model field ([#8](https://github.com/wingfold-ai/bundlemcp/pull/8)) — 2026-09-02

Every model field carries a description.

### refactor(core): Replace the remaining dataclasses with Pydantic models ([#7](https://github.com/wingfold-ai/bundlemcp/pull/7)) — 2026-09-02

The remaining dataclasses replaced with Pydantic models.

### refactor(lifespan): Extract the composition root and make GatewayRuntime honest ([#6](https://github.com/wingfold-ai/bundlemcp/pull/6)) — 2026-09-02

The composition root extracted from the app lifespan.

### refactor(auth): Give the oauth package proper dependency injection ([#5](https://github.com/wingfold-ai/bundlemcp/pull/5)) — 2026-09-02

The OAuth package gets proper dependency injection.

### refactor(router): Rename the injected service parameter from svc to service ([#4](https://github.com/wingfold-ai/bundlemcp/pull/4)) — 2026-09-02

Injected service parameters renamed from `svc` to `service`.

### chore(docs): Document the Pydantic, field and local-aliasing conventions ([#3](https://github.com/wingfold-ai/bundlemcp/pull/3)) — 2026-09-02

The Pydantic, field and local-aliasing conventions documented.

### fix(ci-cd): Stop the encrypted-at-rest assertion failing by chance ([#9](https://github.com/wingfold-ai/bundlemcp/pull/9)) — 2026-09-02

An encrypted-at-rest test no longer fails by chance.

### feat(gateway): Implement the MCP bundling gateway (registry, bundles, endpoints, auth, admin UI) ([#2](https://github.com/wingfold-ai/bundlemcp/pull/2)) — 2026-07-04 to 2026-08-31

The initial implementation: upstream registry and tool discovery, bundles and curation, client-shaped endpoints, the
bidirectional MCP proxy, the OAuth 2.1 server, API keys, admin sign-in through OIDC, upstream OAuth, rate limits, the
audit log, the metering hook, bootstrap, the compose stack and the admin UI. Built from the branches merged between
2026-07-08 and 2026-08-31.
