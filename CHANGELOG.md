# Changelog

Every release of bundlemcp, newest first. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and versions follow [Semantic Versioning](https://semver.org/). Each entry names the metering-hook protocol version it
ships (`METERING_PROTOCOL_VERSION`), so a hook author can tell from the changelog alone whether a release changes the
contract their hook implements. [CONTRIBUTING.md](CONTRIBUTING.md#cutting-a-release) says how a release is cut.

## [Unreleased]

Metering-hook protocol: 2

### Added

- The first release line: upstream MCP servers over Streamable HTTP, composed into bundles and served through
  endpoints shaped per client (`default`, `oauth_only`, `write_as_read`), with an OAuth 2.1 server toward MCP clients,
  API keys, a management API under `/api/v1`, an admin UI, and a metering hook in process or over HTTP.
- Tagged releases: a `v<major>.<minor>.<patch>` tag publishes both images under that version and a GitHub release
  from this file, after the documented restore has been rehearsed against the compose stack.
