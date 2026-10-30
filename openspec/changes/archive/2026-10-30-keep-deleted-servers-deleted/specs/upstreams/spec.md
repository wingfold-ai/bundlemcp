## ADDED Requirements

### Requirement: UPS-40 A discovery never undoes a concurrent change
A discovery MUST NOT undo a change made to its server while it ran. Deleting a server SHALL wait for a discovery of
that server already running, on any replica, and a discovery that starts while the server is being deleted SHALL wait
for the delete and then report that the server was not found. A discovery SHALL store only what it found out about the
server — advertised capabilities, negotiated revision, health, connection state and when it last discovered — and
SHALL store it onto the server as it is stored at that moment: it never re-creates a server that no longer exists, and
then stores no tool, prompt or resource entry or listing for it. A rename or a configuration change saved while a
discovery runs is therefore kept. A failure or success a live call records changes the server's health the same way.

#### Scenario: Deleting an upstream while it is being refreshed
- **GIVEN** `POST /api/v1/upstreams/u1:refresh-tools` is waiting on `u1`'s probe
- **WHEN** `DELETE /api/v1/upstreams/u1` is called
- **THEN** the delete answers 204 once the refresh has finished, and from then on `GET /api/v1/upstreams/u1` answers
  404 and `u1` is not listed

#### Scenario: A server removed under a running discovery stays removed
- **GIVEN** a discovery of `u1` is waiting on `u1`'s probe
- **WHEN** `u1` is removed from the store without waiting for it, and the probe then answers
- **THEN** the discovery reports the server not found, `u1` stays removed, and no tool of `u1` is stored

#### Scenario: A rename during a discovery is kept
- **GIVEN** a discovery of `u1` is waiting on `u1`'s probe
- **WHEN** `u1` is renamed to `u2`, and the probe then answers
- **THEN** the server is still named `u2`, with the capabilities and connection state the discovery found
