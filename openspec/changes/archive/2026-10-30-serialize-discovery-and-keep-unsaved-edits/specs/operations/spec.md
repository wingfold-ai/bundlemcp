## MODIFIED Requirements

### Requirement: OPS-15 Live log page
The admin UI SHALL show a page that streams new buffer entries from the management API (a server-push stream,
admin-authenticated) with pause and resume, a level filter, and free-text, upstream and endpoint filters. Resuming
after a pause or a dropped connection continues from the last entry shown, as long as it is still in the buffer.
While the page is paused no entry SHALL be added to it, including entries from a load of recent entries that was
still in flight when the admin paused.

#### Scenario: New entries appear without reload
- **GIVEN** an admin has the live log page open
- **WHEN** the gateway logs an event at or above the threshold
- **THEN** it appears on the page within a few seconds, without a reload

#### Scenario: Filters narrow the stream
- **WHEN** the admin filters by endpoint `b1-api` and level `ERROR`
- **THEN** only entries for that endpoint at `ERROR` or above are shown

#### Scenario: Resume continues where the page paused
- **GIVEN** the admin paused the stream and three events were logged since
- **WHEN** the admin resumes
- **THEN** the three events are shown in order, without duplicates

#### Scenario: A pause during a load stops the load
- **GIVEN** the admin changed a filter and the page is still loading the recent entries that match it
- **WHEN** the admin pauses before the load answers
- **THEN** the page shows no entry from that load while paused, and resuming loads the entries that match the filter

#### Scenario: Non-admins are refused
- **WHEN** the log stream is requested without an admin session or service API key
- **THEN** the request is refused as unauthenticated
