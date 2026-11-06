# Spec Delta

## ADDED Requirements

### Requirement: DEP-16 The development stack runs only what CI can run
Every service the development compose files define SHALL use an image that is built from this repository or pulled
from a public registry, so CI starts the same stack a contributor does. No service, profile or seed file SHALL depend
on a private image or on credentials of an outside service.

#### Scenario: Every compose image is reachable without credentials
- **WHEN** the hermetic test suite reads the development compose files
- **THEN** every service either builds from a directory in this repository or names a public image pinned by digest
  ([DEP-15](spec.md))

#### Scenario: CI starts the whole stack
- **WHEN** CI brings up the development stack for the integration suite
- **THEN** no service is left out because its image cannot be pulled, and no test is skipped because of one

### Requirement: DEP-17 Identity forwarding is verified against a demo upstream
The integration suite SHALL verify, on every pull request, what an upstream learns about its caller. It runs against
an example upstream in the development stack that reports the identity it received, so no maintainer's own server or
outside account is needed. The behaviours covered are header forwarding, the identity header, introspection of
forwarded bearers and static discovery headers ([auth](../auth/spec.md), [upstreams](../upstreams/spec.md)).

#### Scenario: A forwarded bearer is introspected to the caller
- **GIVEN** the demo upstream forwards `authorization` and introspects the bearer it receives
- **WHEN** a signed-in user calls its identity tool through an OAuth endpoint
- **THEN** the tool reports the user's `sub`, and an API-key caller is reported as `api_key:<id>`

#### Scenario: Discovery authenticates with a static header
- **GIVEN** the demo upstream refuses requests without a credential
- **WHEN** an admin forces a tool discovery of it
- **THEN** discovery succeeds through its static header and finds its tools

#### Scenario: The identity header cannot be spoofed
- **WHEN** an API-key caller sends `X-MCP-User: spoofed` to the demo upstream's identity tool
- **THEN** the tool reports `X-MCP-User` as `api_key:<id>`

#### Scenario: Only mapped headers arrive
- **WHEN** a caller sends a mapped tenant header and a header the upstream does not map
- **THEN** the tool reports the tenant value under its upstream name and does not list the unmapped header

#### Scenario: Callers never see each other's identity
- **WHEN** an OAuth caller and an API-key caller call the identity tool alternately on one gateway
- **THEN** every reply reports the identity of the caller that made that call

#### Scenario: The suite runs without a marker
- **WHEN** CI runs the integration suite
- **THEN** the identity-forwarding tests run with every other test, and no marker excludes them

## MODIFIED Requirements

### Requirement: DEP-15 Images are pinned by digest
Every image a Dockerfile builds from or copies from, and every image the compose files run, SHALL be referenced by a
version tag and its content digest, never by a moving tag alone, so a rebuild uses the bytes CI tested. Automated
update pull requests keep tags and digests current. There is no exception: an image a compose file takes from a
variable is pinned in that variable's default too.

#### Scenario: An unpinned image fails the tests
- **GIVEN** a Dockerfile or compose file that names `node:26-alpine` or `example/image:latest` without a digest
- **WHEN** the hermetic test suite runs
- **THEN** it fails and names the file, the line and the image

#### Scenario: A moved tag does not change the build
- **GIVEN** a base image whose tag the publisher has since pointed at new contents
- **WHEN** the gateway image is rebuilt from an unchanged checkout
- **THEN** it is built from the same base image contents as before

#### Scenario: Pinned images still name their runtime version
- **GIVEN** the gateway's base image is referenced as `python:3.15.1-slim-bookworm@sha256:<digest>`
- **WHEN** the runtime-version check ([ARC-2](../architecture/spec.md)) runs
- **THEN** it reads Python `3.15` from that reference

#### Scenario: A variable-chosen image is pinned too
- **GIVEN** a compose service whose image is `${SOME_IMAGE:-example/image:latest}`
- **WHEN** the hermetic test suite runs
- **THEN** it fails on the unpinned default, whatever profile the service belongs to
