## ADDED Requirements

### Requirement: UPS-39 Discoveries of one server do not overlap
Discoveries of the same server MUST NOT overlap, on one replica or across replicas: a discovery that starts while
another discovery of that server is running SHALL wait until the other has stored its result, then probe and compare
against what it stored. Concurrent triggers, such as the background probe after a save and an explicit refresh, SHALL
therefore never store a tool or a prompt or resource entry twice, and an explicit refresh SHALL never fail because of
a concurrent discovery. Discoveries of different servers still run in parallel.

#### Scenario: A refresh right after a save
- **GIVEN** saving upstream `u1` scheduled a background discovery
- **WHEN** `POST /api/v1/upstreams/u1:refresh-tools` is called before that discovery finished
- **THEN** the refresh answers 200 with the discovery result, and each of `u1`'s tools is cached once

#### Scenario: Refreshes on two replicas at once
- **WHEN** a refresh of the same upstream is requested on two replicas at the same time
- **THEN** both answer 200, and the upstream's tools are cached once each

#### Scenario: Different servers are not held up
- **WHEN** a discovery of `u1` is waiting on an unanswered probe
- **THEN** a discovery of `u2` runs and completes without waiting for it
