# Spec Delta

## MODIFIED Requirements

### Requirement: DOC-3 Demo seed
The dev compose stack MUST ship a demo bootstrap file ([management](../management/spec.md)), `deploy/seed.yaml`,
registering at least a small example MCP server container (`examples/echo-mcp`), one bundle, and one
`default`-profile endpoint — a fresh install is never empty and the quickstart has something to click. It also
registers the identity demo (`examples/identity-demo-mcp`), which reports what it learns about its caller, in a bundle
and endpoint of its own, so the demo bundle's tools stay those of the quickstart.

#### Scenario: Fresh install is not empty
- **WHEN** the compose stack starts against an empty database
- **THEN** the `echo` server, the `demo` bundle and the `default`-profile `demo` endpoint exist without any manual step

#### Scenario: The identity demo has its own endpoint
- **WHEN** the compose stack starts against an empty database
- **THEN** the `identity-demo` server, the `identity` bundle and the `identity` endpoint exist, and the `demo` bundle
  does not contain `identity-demo`
