# Changelog

Every release of bundlemcp, newest first. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and versions follow [Semantic Versioning](https://semver.org/). Each entry names the metering-hook protocol version it
ships (`METERING_PROTOCOL_VERSION`), so a hook author can tell from the changelog alone whether a release changes the
contract their hook implements. [CONTRIBUTING.md](CONTRIBUTING.md#cutting-a-release) says how a release is cut.

## [Unreleased]

Metering-hook protocol: 2

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
