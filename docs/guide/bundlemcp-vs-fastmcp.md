# bundlemcp vs. FastMCP: Gateway vs. Framework

A common question when evaluating bundlemcp is:

> *"Can't I just expose my tools directly using FastMCP? What does bundlemcp do differently, and what value does it add?"*

The short answer: **FastMCP is a framework for building individual MCP servers. bundlemcp is an infrastructure gateway for operating, aggregating, and securing multiple MCP servers in production.** 

In fact, bundlemcp does not replace FastMCP — it uses FastMCP internally as its upstream client engine.

---

## The Core Distinction

```
Consuming Clients (Claude.ai, ChatGPT, Agents, CI/CD)
         │
         ▼
┌─────────────────────────────────────────┐
│                bundlemcp                │  ◀── Gateway & Aggregation Layer
│  • Single URL for 10+ servers           │      • OAuth 2.1 & API Key auth
│  • Valkey cluster sessions              │      • Rate limits & brute force defense
│  • Per-client shaping & tool curation   │      • Audit logs & billing metering
└────────────────────┬────────────────────┘
                     │ (Streamable HTTP)
         ┌───────────┴───────────┐
         ▼                       ▼
 ┌───────────────┐       ┌───────────────┐
 │ Upstream MCP  │       │ Upstream MCP  │   ◀── Application Framework
 │   (FastMCP)   │       │ (FastMCP / TS)│       • Tool implementation (@mcp.tool)
 │   GitHub Ops  │       │  Postgres DB  │       • Prompt / resource definitions
 └───────────────┘       └───────────────┘
```

- **Use FastMCP when:** You want to author tools in Python. FastMCP provides a great developer experience for defining `@mcp.tool()` functions, prompts, and resources.
- **Use bundlemcp when:** You have one or more MCP servers and need to serve them to real users, LLMs, or production agents with enterprise requirements: horizontal scaling, authentication, auditing, and per-client shaping.

---

## Comparison Matrix

| Capability | FastMCP (Server Framework) | bundlemcp (Bundling Gateway) |
|---|---|---|
| **Primary Purpose** | Tool authoring and standalone server execution. | Gateway proxy, bundling, security, and traffic governance. |
| **Session Architecture** | **In-Memory:** Sessions and connection state reside in Python process memory. A process restart terminates all active client sessions (`404 Session not found`). | **Horizontally Scalable Live State:** Sessions reside in Valkey (Redis). Any gateway replica serves any request without sticky sessions; restarts are zero-downtime non-events. |
| **Multi-Server Aggregation** | Runs as a single server on its own port. | Aggregates unlimited upstream servers into unified virtual **Bundles** with namespacing (`server__tool`) to eliminate name collisions. |
| **Client Shaping** | Exposes a static, uniform schema to all callers. | **Endpoint Profiles:** Exposes the same bundle through multiple endpoints shaped for specific consumers (e.g. re-annotating write tools as read-safe for ChatGPT, hiding uncurated tools). |
| **Client Authentication** | None built-in (relies on custom transport wrappers). | **Turnkey Auth Gateway:** Built-in OAuth 2.1 server (RFC 7591 dynamic client registration + PKCE for Claude.ai), API keys (`bmcp_sk_...`), and OIDC federation (Keycloak, Auth0) for admin UI. |
| **Upstream Authentication** | Unaware of downstream caller identity. | **Upstream OAuth & Identity Propagation:** Injects per-user OAuth tokens (GitHub, Slack) and forwards `X-MCP-User` identity headers to upstreams. |
| **Operational Governance** | No audit logging, rate limiting, or metering. | Centralized structured audit logs (`AuditSink`), IP brute-force lockout, fixed-window rate limiting, and credit/billing interception hooks (`MeteringHook`). |
| **Protocol Compatibility** | Fixed to the SDK revision it was built against. | **Dual-Era Gateway:** Accepts Stateless (Copilot/modern) and Session (Claude/ChatGPT/Cursor) MCP requests simultaneously on a single URL. |

---

## Key Values bundlemcp Delivers

### 1. Zero-Downtime Rolling Restarts & Horizontal Scaling
Standard MCP servers maintain connection pools and session IDs in local memory. When deployed behind a load balancer or Kubernetes ingress, this causes two critical failure modes:
1. Replicas cannot share sessions without sticky session affinity.
2. Any deployment, restart, or worker crash instantly drops all client connections with `404 Session not found`.

bundlemcp solves this by storing all durable state in Postgres and all live sessions in Valkey. A client session is pure data: any replica can serve any request, and gateway restarts never interrupt active client conversations.

### 2. Multi-Server Sprawl Eliminated
Instead of requiring users to register 5 to 10 distinct connection URLs in Claude or Cursor, bundlemcp lets operators register servers once, curate tools into logical bundles (e.g. `engineering-bundle`, `analytics-bundle`), and hand users a single stable connection URL.

### 3. Work Around Client Quirks Without Changing Server Code
Different LLM clients enforce conflicting constraints:
- **Claude.ai** requires a strict OAuth 2.1 authorization server with dynamic client registration and metadata discovery endpoints.
- **ChatGPT** refuses MCP write tools unless they are explicitly re-annotated as read-safe.
- **CI/CD scripts and local agents** need direct API key authentication without interactive browser redirects.

With bundlemcp, you author your tools once in FastMCP. You then create multiple **Endpoints** in bundlemcp pointing to the same bundle — one shaped for Claude.ai with OAuth, one with read-safe re-annotations for ChatGPT, and one authenticated by API key for automation.

### 4. Enterprise Auditability & Billing
bundlemcp provides a unified audit trail recording caller identity, endpoint, upstream server, tool name, execution duration, and outcome status across all aggregated tools. Its `MeteringHook` allows commercial platforms to enforce check-and-debit credit balances before driving upstream calls.
