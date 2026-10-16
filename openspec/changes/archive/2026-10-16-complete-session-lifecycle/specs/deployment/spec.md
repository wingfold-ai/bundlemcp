## MODIFIED Requirements

### Requirement: DEP-7 Restart survival is tested
Zero-downtime deployment MUST be verified by the integration suite against the compose stack: the restart-under-load
test of [SES-12](../sessions/spec.md) runs while two gateway replicas are replaced one at a
time by a rolling `compose up` of a newly built image. Sessions established before the rollout keep working afterwards
without re-initializing, and no request sent during it is answered 404 or 500.

#### Scenario: Session survives a gateway restart
- **GIVEN** a session initialized on the `demo` endpoint
- **WHEN** the gateway container restarts and becomes ready again
- **THEN** `tools/list` with the same `Mcp-Session-Id` returns the tools

#### Scenario: Rolling update under load
- **GIVEN** two gateway replicas behind a round-robin proxy and clients sending requests on open sessions
- **WHEN** a new gateway image is built and the replicas are replaced one at a time, each waiting for the other to be
  ready
- **THEN** every request sent during the rollout succeeds or is answered with a retryable 503, none with 404 or 500
- **AND** every session serves `tools/list` afterwards without re-initializing
