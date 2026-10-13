# ADR-0043: The gateway contacts an upstream only when it has a reason to

**Status:** accepted · **Date:** 2026-10-12 · **Amends:** [ADR-0021](0021-mcp-surface-completion.md)

## Context

Upstream MCP servers are increasingly deployed to scale to zero when idle: a Kubernetes Deployment behind the KEDA HTTP
add-on, Knative, or a similar interceptor. Any request that reaches such a server wakes it. For it to stay at zero, the
gateway should contact it only while serving a call that needs it.

`initialize` and `tools/list` already meet that bar, because they are served from the discovery cache. Issue #93 found
two paths that did not:

- **Every server upsert scheduled a discovery probe**, including one that changed nothing
  ([UPS-2](../../openspec/specs/upstreams/spec.md)). Declarative setups re-apply every server on every deploy,
  and a bootstrap file is re-applied on every gateway start ([MGMT-9](../../openspec/specs/management/spec.md)). On
  Kubernetes that is every rollout, restart and new replica, and each one woke every upstream.
- **Prompt and resource methods fanned out live to every member** ([BND-8](../../openspec/specs/bundles/spec.md)),
  including members whose discovery snapshot did not advertise prompts or resources. Clients such as claude.ai list
  prompts and resources right after connecting, so connecting a client woke every server in the bundle to answer with an
  empty list.

The third path, the periodic refresh ([ADR-0038](0038-periodic-tool-refresh.md)), already has an off switch.

## Decision drivers

- An idle upstream that scales to zero stays at zero unless a client actually needs it.
- What clients see does not change for upstreams that are always on.
- One rule in the gateway, not a workaround in every client of the admin API.

## Decision

- **An update probes only when it changes what discovery depends on.** `McpServer.discovery_inputs` names those fields:
  `url`, `static_headers`, `forward_headers`, `auth_mode`, `identity_mode`, `send_identity_header` and `protocol_mode`.
  `ServerService.upsert` compares them before and after the write. It also probes when the last probe did not succeed
  (`connection_state` other than `ready`), so re-applying a config still retries a server that was down when it was
  registered. A create always probes; explicit refresh and inspection always contact the upstream. Bootstrap goes
  through the same `upsert`, so it inherits the rule.
- **Fan-out asks only members that advertise the capability.** `MemberFanout` filters members by their capabilities
  snapshot ([UPS-22](../../openspec/specs/upstreams/spec.md)): `prompts` for `prompts/*`, `resources` for
  `resources/*`, `completions` for `completion/complete`. A member that was never discovered has an empty snapshot and
  is skipped, which matches what `initialize` already advertises for it
  ([PROT-11](../../openspec/specs/protocol/spec.md)).

## Alternatives considered

- **Compare desired and stored state in the deploy tooling.** Works, but every client of the admin API would have to
  re-implement it, and the bootstrap file would still wake every upstream on every gateway start.
- **Serve prompt and resource lists from a cached snapshot.** Would let a server that does advertise prompts stay idle
  too, but adds a second cache with its own staleness rules. Left for a later decision; the capability filter covers
  the common case of tool-only servers.
- **Exclude a server from fan-out by a per-server setting.** An operator knob for what the capabilities snapshot
  already says.

## Consequences

**Positive:**

- A bundle of tool-only upstreams can be connected to, listed and re-deployed without waking any of them.
- A deploy that re-applies an unchanged config no longer causes a burst of discovery probes.

**Trade-offs:**

- A server whose snapshot is stale — it started advertising prompts after its last discovery — is not asked for them
  until the next discovery. The periodic refresh or an explicit refresh closes that gap.
- Re-applying an unchanged config to a working server no longer refreshes its tools as a side effect. An operator who
  relied on that uses the explicit refresh.
