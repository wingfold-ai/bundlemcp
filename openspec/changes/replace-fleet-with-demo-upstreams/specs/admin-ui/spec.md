# Spec Delta

## MODIFIED Requirements

### Requirement: UI-13 Admin UI verified in CI
CI SHALL run every browser scenario of the admin UI against the development stack for every pull request, and SHALL
run unit tests for the UI's pure logic: name validation, the tool-argument form, the prompt preview and the
invalidation of the query cache. A failing scenario or unit test SHALL fail the run. No scenario is excluded from the
run, by a marker or otherwise.

#### Scenario: A broken page fails CI
- **GIVEN** a change that breaks adding a member on the bundle detail page
- **WHEN** CI runs for the pull request
- **THEN** the integration job fails on the browser scenario that adds a member

#### Scenario: A broken validation rule fails CI
- **GIVEN** a change that lets the name validation accept `my__server` as an upstream name
- **WHEN** CI runs for the pull request
- **THEN** the frontend job fails on the unit test for upstream names

#### Scenario: A new browser scenario runs without a CI edit
- **WHEN** a contributor adds a browser scenario
- **THEN** the next CI run executes it without any change to the workflow
