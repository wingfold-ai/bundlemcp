# Changelog

Every release of bundlemcp, newest first. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and versions follow [Semantic Versioning](https://semver.org/). Each entry names the metering-hook protocol version it
ships (`METERING_PROTOCOL_VERSION`), so a hook author can tell from the changelog alone whether a release changes the
contract their hook implements. [CONTRIBUTING.md](CONTRIBUTING.md#how-a-release-happens) says how a
release happens.

## [0.1.1] - 2026-10-15

Metering-hook protocol: 2

### Added

- Make every pull request carry its own release ([#134](https://github.com/wingfold-ai/bundlemcp/pull/134))

## [0.1.0] - 2026-10-15

Metering-hook protocol: 2

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
