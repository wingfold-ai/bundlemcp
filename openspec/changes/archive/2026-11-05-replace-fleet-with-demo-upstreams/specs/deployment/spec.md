## MODIFIED Requirements

### Requirement: DEP-15 Images are pinned by digest
Every image a Dockerfile builds from or copies from, and every image the compose files run, SHALL be referenced by a
version tag and its content digest, never by a moving tag alone, so a rebuild uses the bytes CI tested. Automated
update pull requests keep tags and digests current. No image is exempt, including one a compose file takes from a
variable.

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

#### Scenario: An image chosen through a variable is pinned too
- **WHEN** a compose service takes its image from a variable such as `${OTHER_IMAGE:-example/image:latest}`
- **THEN** a default without a digest fails the test like any other unpinned image
