## MODIFIED Requirements

### Requirement: ARC-8 RESP store holds live state
The RESP store MUST hold the live state: MCP session state, upstream session bindings, rate-limit counters, the
live-log ring buffer ([OPS-14](../operations/spec.md)), cross-replica pub/sub. The store never holds configuration;
outage behavior is explicitly defined in the degradation matrix
([SES-14](../../../../specs/sessions/spec.md)) — bounded, honest degradation, not silent failure. The store
is a **RESP-compatible** server — the default is **Valkey** (BSD-3), accessed via the MIT `redis-py` client
([ADR-0022](../../../../../docs/adr/0022-valkey-store.md)); "Redis" elsewhere in these specs denotes this RESP
store/protocol, not the Redis product specifically.

#### Scenario: Session records live in the RESP store
- **WHEN** a client initializes a session against an endpoint
- **THEN** the session record is written to the RESP store, not to process memory

#### Scenario: Config changes travel over pub/sub
- **WHEN** a config-class record is changed through the management API
- **THEN** an invalidation event is published on the RESP store's invalidation channel after the commit

#### Scenario: The live-log buffer lives in the RESP store
- **WHEN** a replica logs an event at or above the live-log threshold
- **THEN** the event is appended to the capped log stream in the RESP store, not kept in process memory
