## ADDED Requirements

### Requirement: UI-12 Errors shown where they happened
On a detail page made of several cards, an action that fails SHALL show its error on the card whose action failed,
whether the client-side validation or the API refused it, and nowhere else on the page. Starting another action on a
card SHALL clear only that card's error. A failure to load the page's own data SHALL still be shown at the top of the
page.

#### Scenario: A curation error stays on the curation card
- **GIVEN** a bundle with a member tool
- **WHEN** the admin enters an annotation override that is not a JSON object and saves that tool's row
- **THEN** the tool curation card shows the error, and the page top and every other card show none

#### Scenario: An API refusal is shown on the card that sent it
- **GIVEN** upstream `echo` is a member of a bundle
- **WHEN** the admin renames it without acknowledging the consequence and the API refuses the rename
- **THEN** the refusal is shown on the card holding the rename control, and the configuration card shows no error

#### Scenario: Errors on two cards are independent
- **GIVEN** the members card of a bundle shows an error from a failed member change
- **WHEN** the admin saves the bundle's description successfully
- **THEN** the members card still shows its error, and the meta card shows none

#### Scenario: A failed load is shown at the page top
- **GIVEN** the gateway fails to return a bundle's tools
- **WHEN** the admin opens the bundle's detail page
- **THEN** the load error is shown at the top of the page

### Requirement: UI-13 Admin UI verified in CI
CI SHALL run every browser scenario of the admin UI against the core stack, the stack without the fleet profile, for
every pull request, and SHALL run unit tests for the UI's pure logic: name validation, the tool-argument form, the
prompt preview and the invalidation of the query cache. A failing scenario or unit test SHALL fail the run. A scenario
that needs images CI cannot pull is excluded by a marker in its title, never by omission from the run.

#### Scenario: A broken page fails CI
- **GIVEN** a change that breaks adding a member on the bundle detail page
- **WHEN** CI runs for the pull request
- **THEN** the integration job fails on the browser scenario that adds a member

#### Scenario: A broken validation rule fails CI
- **GIVEN** a change that lets the name validation accept `my__server` as an upstream name
- **WHEN** CI runs for the pull request
- **THEN** the frontend job fails on the unit test for upstream names

#### Scenario: A new browser scenario runs without a CI edit
- **WHEN** a contributor adds a browser scenario that needs only the core stack
- **THEN** the next CI run executes it without any change to the workflow
