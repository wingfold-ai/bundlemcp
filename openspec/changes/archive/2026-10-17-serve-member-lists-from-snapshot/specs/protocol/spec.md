## MODIFIED Requirements

### Requirement: PROT-10 Upstream list changes
Upstream `notifications/tools/list_changed`, `notifications/prompts/list_changed` and
`notifications/resources/list_changed`, received on a pooled upstream session during or between calls, SHALL trigger
re-discovery of that server ([UPS-17](../upstreams/spec.md)) and be propagated to the connected
clients of every bundle the server is an enabled member of, per [BND-7](../bundles/spec.md): on the GET
stream for handshake clients, on the `subscriptions/listen` stream for modern clients (PROT-17). The re-discovery
MUST finish before a prompt or resource list change is propagated, so a client that lists again is served the
refreshed listing snapshot ([UPS-24](../upstreams/spec.md)). The same change announced to several replicas' sessions
MUST trigger one re-discovery, not one per replica.

#### Scenario: Tool list change between calls
- **GIVEN** a handshake client holds a GET stream on an endpoint whose bundle contains server `echo`
- **WHEN** `echo` sends `notifications/tools/list_changed` while no call is in flight
- **THEN** `echo` is re-discovered and the client's GET stream receives `notifications/tools/list_changed`

#### Scenario: Member prompt list change reaches a modern listener
- **WHEN** a modern client listens with `promptsListChanged` and a member sends `notifications/prompts/list_changed`
- **THEN** the client's listen stream receives `notifications/prompts/list_changed` tagged with its subscription id

#### Scenario: A prompt list change refreshes the snapshot
- **GIVEN** member `echo`'s prompt snapshot lists `greet`, and `echo` has since added prompt `farewell`
- **WHEN** `echo` sends `notifications/prompts/list_changed` and a client then calls `prompts/list`
- **THEN** the list shows `echo__farewell`

#### Scenario: One re-discovery for several replicas
- **GIVEN** replicas A and B each hold a pooled session to `echo`
- **WHEN** `echo` announces one tool list change on both sessions
- **THEN** discovery for `echo` runs once
