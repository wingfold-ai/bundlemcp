## MODIFIED Requirements

### Requirement: MGMT-13 Demo bootstrap
The dev compose stack SHALL ship a demo bootstrap file ([DOC-3](../documentation/spec.md)) so a fresh install
starts non-empty. Besides the demo bundle it SHALL register an upstream that verifies its callers by introspecting
the bearer the gateway forwards ([AUTH-30](../auth/spec.md)) and reports what reached it, so header passthrough is
tested against the stack without any third-party server.

#### Scenario: Demo seed is valid
- **WHEN** `deploy/seed.yaml` is parsed as a bootstrap document
- **THEN** it validates and declares at least one upstream, bundle and endpoint

#### Scenario: The stack tests header passthrough on its own
- **GIVEN** the compose stack started with nothing but its defaults
- **WHEN** a caller calls the introspecting upstream's tool through its endpoint
- **THEN** the upstream reports the subject the gateway's introspection named for that caller, and the identity
  header it received
