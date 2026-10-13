## MODIFIED Requirements

### Requirement: UPS-18 Hash-based sync
Sync is hash-based: the gateway MUST compute a stable hash per tool definition and rewrite a cached definition only when
its hash changed (metamcp's `tools-sync-cache` behavior). A discovery run in which no tool is new, changed, vanished or
reappeared MUST NOT write any cached tool, so the common case is write-free. A new, changed, vanished or reappearing
tool counts as a change of the tool set ([BND-7](../bundles/spec.md)); an unchanged tool does not.

#### Scenario: Unchanged definition is not rewritten
- **WHEN** discovery sees a tool whose definition hash equals the cached `schema_hash`
- **THEN** its definition columns are left as they were and the run reports zero changes

#### Scenario: Unchanged run writes no tool
- **WHEN** discovery of a server lists exactly the tools it listed on the previous successful run, with unchanged
  definitions
- **THEN** no cached tool of that server is written and no bundle is invalidated

#### Scenario: Changed definition is rewritten
- **WHEN** an upstream changes a tool's description
- **THEN** the cached definition and `schema_hash` are updated and the run reports one change

### Requirement: UPS-19 Vanished tools are kept
Tools that disappear from the upstream MUST NOT be deleted automatically: a tool that the latest successful discovery
of its server did not list is **stale**. A stale tool MUST NOT be served — it is absent from every endpoint's
`tools/list` and rejected on `tools/call` like an unknown tool — but keeps its `BundleTool` curation, and is served
again, with that curation, if a later discovery lists it. A failed probe makes no tool stale. The management API and
UI report which tools are stale. Explicit deletion MUST be available as "refresh & prune" in the API and UI: a refresh
that, only when its probe succeeds, deletes the server's stale tools together with their curation in every bundle.

#### Scenario: A vanished tool stays cached
- **WHEN** an upstream that listed `alpha` and `beta` is rediscovered listing only `alpha`
- **THEN** both tools remain cached, `beta` keeps its curation and is reported stale
- **AND** `tools/list` on an endpoint of a bundle containing the upstream lists `alpha` but not `beta`, and a call to
  `beta` is rejected as an unknown tool without contacting the upstream

#### Scenario: A reappearing tool is served with its curation
- **GIVEN** stale tool `beta` with `override_name` `b` in a bundle
- **WHEN** a later discovery lists `beta` again
- **THEN** `beta` is no longer stale and is listed as `b` on the bundle's endpoints

#### Scenario: A failed probe makes nothing stale
- **WHEN** discovery of a server fails
- **THEN** none of its cached tools becomes stale

#### Scenario: Refresh and prune deletes stale tools
- **GIVEN** a server with stale tool `beta`
- **WHEN** an admin calls `POST /api/v1/upstreams/{name}:refresh-tools?prune=true` and the probe succeeds
- **THEN** `beta` and its curation in every bundle are deleted and the response reports one pruned tool

#### Scenario: Prune after a failed probe deletes nothing
- **WHEN** an admin calls `POST /api/v1/upstreams/{name}:refresh-tools?prune=true` and the probe fails
- **THEN** no tool is deleted and the response reports the failure
