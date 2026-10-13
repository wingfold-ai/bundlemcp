## MODIFIED Requirements

### Requirement: DEP-2 Trusted proxies decide the client IP
Trusted-proxy config (`BUNDLEMCP_TRUSTED_PROXIES`, CIDR list): `X-Forwarded-For` MUST be honored only when the direct
peer is in the list; otherwise it is ignored and the socket peer is the client IP. The client IP used for rate limiting
([EP-16](../../../../specs/endpoints/spec.md)), the auth-failure lockout, per-IP client-registration limits and
logging ([OPS-8](../../../../specs/operations/spec.md)) derives from this policy — XFF from untrusted peers is never
believed ([ADR-0018](../../../../../docs/adr/0018-rate-limiting.md)). When the peer is trusted, the leftmost XFF entry
is taken.

#### Scenario: Untrusted peer cannot spoof its IP
- **GIVEN** `BUNDLEMCP_TRUSTED_PROXIES` is empty
- **WHEN** a request from `203.0.113.7` carries `X-Forwarded-For: 10.0.0.1`
- **THEN** the client IP is `203.0.113.7`

#### Scenario: Trusted proxy forwards the client IP
- **GIVEN** `BUNDLEMCP_TRUSTED_PROXIES=["172.16.0.0/12"]`
- **WHEN** a request from `172.18.0.2` carries `X-Forwarded-For: 198.51.100.4, 172.18.0.1`
- **THEN** the client IP is `198.51.100.4`

#### Scenario: Logs carry the derived client IP
- **GIVEN** `BUNDLEMCP_TRUSTED_PROXIES=["172.16.0.0/12"]`
- **WHEN** a request from `172.18.0.2` carrying `X-Forwarded-For: 198.51.100.4` is served
- **THEN** its log lines, the access log line included, carry `client_ip` `198.51.100.4`, not the proxy's address

### Requirement: DEP-4 Migrations as a guarded dedicated step
Alembic migrations MUST run as a **dedicated step** (the gateway image's entrypoint runs `alembic upgrade head` before
starting the server, or an operator runs it as a one-shot pre-deploy job) guarded by a Postgres advisory lock — N
replicas starting concurrently never double-run. A replica does not bind its port, and so serves nothing, until the
migration step has finished. A replica whose database schema is behind the migration head it ships with SHALL report
`/readyz` not ready ([OPS-10](../../../../specs/operations/spec.md)) until the schema is current.

#### Scenario: Concurrent replicas migrate once
- **WHEN** two replicas of a newer image start at the same time against the same database
- **THEN** one applies the migration while the other waits on the advisory lock and then finds nothing to do

#### Scenario: Replica waits for a one-shot migration job
- **GIVEN** a newer image started without the entrypoint migration step, against a database one migration behind
- **WHEN** an orchestrator polls `/readyz`
- **THEN** it answers 503 until the one-shot migration job has applied the head, and 200 afterwards
