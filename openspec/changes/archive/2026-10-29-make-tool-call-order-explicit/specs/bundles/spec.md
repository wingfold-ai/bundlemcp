## ADDED Requirements

### Requirement: BND-38 Concurrent live list fan-out
When `prompts/list`, `resources/list` or `resources/templates/list` has to ask more than one member live
([BND-8](../bundles/spec.md)), the gateway SHALL send those requests concurrently, so the list takes about as long as
its slowest member rather than the sum of all of them. Each member still receives one request. The answer SHALL NOT
depend on the order in which members respond: entries are merged and de-duplicated in member order
([BND-1](../bundles/spec.md)).

#### Scenario: Live members are asked at the same time
- **GIVEN** members `alpha` and `beta`, neither with a shareable listing snapshot, where each one answers
  `prompts/list` only after the other has been asked
- **WHEN** a client calls `prompts/list`
- **THEN** the call returns the prompts of both members, and each member received exactly one request

#### Scenario: A later member answering first does not change the order
- **GIVEN** members `zeta` and `alpha`, in that order, both answering `resources/list` live with resource
  `file:///a.txt`, and `alpha` answers before `zeta`
- **WHEN** a client calls `resources/list`
- **THEN** the URI is listed once, taken from `zeta`, and the collision is logged against `alpha`

#### Scenario: A failing member does not hold back the others
- **GIVEN** members `alpha` and `beta` without shareable snapshots, where `alpha`'s request fails
- **WHEN** a client calls `prompts/list`
- **THEN** the list contains `beta`'s prompts, and `alpha`'s failure is logged with its cause
