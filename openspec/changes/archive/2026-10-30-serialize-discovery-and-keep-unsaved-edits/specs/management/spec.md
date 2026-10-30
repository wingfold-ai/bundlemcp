## MODIFIED Requirements

### Requirement: MGMT-6 Retryable writes
Write operations SHALL be safely retryable: upserts by natural key where sensible (MGMT-4), and deletes idempotent —
deleting a resource that does not exist answers 204. A write that collides with a concurrent write on a uniqueness
rule of the store SHALL answer 409 with a message saying it can be retried, never an unhandled 500 or a dropped
connection.

#### Scenario: Deleting a missing resource
- **WHEN** a client calls `DELETE /api/v1/upstreams/ghost` and no such upstream exists
- **THEN** the response is 204

#### Scenario: A colliding write is a conflict
- **WHEN** a write's transaction is refused by the store because a concurrent write stored the same unique key first
- **THEN** the response is 409, its body says the write collided with a concurrent change and can be retried, and the
  connection stays open
