# 12. Glossary

Two vocabularies, split by audience.

**Product vocabulary** — server, bundle, endpoint, profile, presented tool,
caller identity, protocol era, consent, workspace and the rest — is defined once
for readers and operators in [`docs/guide/glossary.md`](../guide/glossary.md),
which is published on the documentation site. It is not repeated here.

What follows is the **implementation vocabulary**: the words this codebase uses
for its own parts, which a new contributor meets in the first hour and will not
find in the product glossary.

## Layers and wiring

| Term | Meaning | Owner |
|---|---|---|
| **Contract** | A `typing.Protocol` the application defines and infrastructure fulfils. Deliberately *not* called a "port": in a network gateway "port" and "protocol" already mean something else ([ADR-0033](../adr/0033-clean-architecture-layers.md)) | `application/contracts/` |
| **Adapter** | One implementation of a contract, grouped by technology | `infrastructure/<tech>/` |
| **Memory fake** | The in-process implementation of a contract that `tests/application` runs on. The fake is what the contract buys | `infrastructure/memory/` |
| **Composition root** | The only place adapters meet use cases; builds everything in dependency order and owns their lifetimes | `main/composition_root.py` |
| **Container** | The typed object holding the composed collaborators, published once on `app.state` ([ADR-0025](../adr/0025-repository-unit-of-work-and-container.md)) | `main/container.py` |
| **Provider** | A FastAPI dependency alias that hands a handler one collaborator. Called a *provider*, not a "dependency", because the thing supplied is a collaborator, not a requirement | `api/http/`, `api/*/providers.py` |
| **Assembly** | A Pydantic model listing everything one subsystem is built from, with a `build()` that wires it | `main/mcp_gateway_assembly.py` |

## Persistence

| Term | Meaning | Owner |
|---|---|---|
| **Entity** | A plain Pydantic model of a domain concept. Imports no ORM ([ADR-0034](../adr/0034-pydantic-entities-and-row-classes.md)) | `domain/<context>/` |
| **Row class** | The SQLModel table for an entity. Also the escape hatch to raw SQLAlchemy | `infrastructure/postgres/rows/` |
| **Repository** | The accessor for one entity, declared as a contract and reached through the unit of work | `application/contracts/persistence/` |
| **Unit of work** | One short transaction per request, exposing the repositories. A mutation not followed by `add` is silently lost | `application/contracts/persistence/unit_of_work.py` |
| **DTO** | An API request or response shape. Never an entity, never a row | `application/schemas/` |

## The MCP gateway

| Term | Meaning | Owner |
|---|---|---|
| **Front controller** | `McpGatewayRouter`: admits a request, then routes it to the adapter for its era ([ADR-0035](../adr/0035-front-controller-protocol-adapters-and-admission-pipeline.md)) | `api/mcp/routing/gateway_router.py` |
| **Admission gate** | The two cheap stages before any database work: parse the envelope, then authenticate in one unit of work | `api/mcp/routing/admission_gate.py` |
| **Protocol adapter** | `StatelessMcpAdapter` or `SessionMcpAdapter`: establishes the protocol facts its era carries, then dispatches | `api/mcp/routing/adapters/` |
| **Dialect** | The revision-specific wire shape — which result fields exist, which error codes, which HTTP status. Handlers never branch on it | `api/mcp/protocol/dialect/` |
| **`ProtocolEra`** | `STATELESS` or `SESSION`. The names `modern`/`handshake` survive only where they mirror the MCP SDK's own vocabulary | `api/mcp/protocol/dialect/era.py` |
| **Method registry** | Maps a JSON-RPC method to its handler class, so adding a method is a registration, not a conditional ([ADR-0027](../adr/0027-mcp-edge-method-handlers.md)) | `api/mcp/dispatch/` |
| **Request context** | An admitted request plus the protocol facts every handler needs, whichever era produced them | `api/mcp/protocol/request_context.py` |
| **Tool call** | The object carrying one `tools/call` through credentials, metering, the upstream call and audit | `api/mcp/tool_call/tool_call.py` |
| **MRTR** | Mid-request tool response: an upstream asks the *client* a question mid-call. Served by pass-through, or by park-and-resume ([ADR-0029](../adr/0029-dialects-and-dual-era-edge.md)) | `api/mcp/relay/` |
| **Park and resume** | Sealing a paused call's state into the client's response so any replica can continue it on the retry. Audited as `input_required` | `api/mcp/relay/parking_channel.py` |
| **Binding** | A session's lazy attachment to one upstream session per member server, keyed by forwarded identity when credentials are forwarded (SES-6) | `api/mcp/tool_call/upstream_call.py` |
| **Routing key** | What a request's streams, calls and signals are addressed by: the session id for a session client, a fresh id per stateless request | `api/mcp/protocol/request_context.py` |

## Live state

| Term | Meaning | Owner |
|---|---|---|
| **Signal bus** | Valkey pub/sub delivering cancels, client replies and events to whichever replica holds the stream | `infrastructure/valkey/` |
| **Stream registry** | This replica's open streams and in-flight calls. Deliberately process-local: a stream *is* a connection | `infrastructure/inprocess/` |
| **Invalidation event** | A cross-replica configuration-invalidation message ([sessions spec](../../openspec/specs/sessions/spec.md)) | `infrastructure/valkey/publish_invalidation.py` |
| **Invalidation bus** | The channel those events travel on, so a config change reaches every replica without a restart | `infrastructure/valkey/` |

## Conventions

| Term | Meaning |
|---|---|
| **Requirement ID** | A stable, testable identifier in `/spec` (`UPS-1`, `EP-3`, `PROT-13`). Belongs in `#` comments, test names and error messages — never in a docstring or a field description |
| **Policy object** | An invariant spanning several resources, as an object rather than a check buried in a service (`PerUserUpstreamPolicy`) |
| **Import contract** | An import-linter rule enforcing the layer direction. Three of them, zero exceptions |

## Acronyms

| Term | Meaning |
|---|---|
| **MCP** | Model Context Protocol |
| **ADR** | Architecture Decision Record ([docs/adr](../adr/README.md)) |
| **LikeC4** | The diagram-as-code DSL the model in [docs/likec4](../likec4/) is written in |
| **DCR** | Dynamic Client Registration (RFC 7591) |
| **RESP** | The Redis Serialization Protocol, which Valkey speaks |
