# Spec Delta

## ADDED Requirements

### Requirement: DOC-16 Public roadmap
The documentation site MUST publish `/roadmap`, linked from its top navigation, as the project's only roadmap. It
draws one line of stations, in order: Now, In progress, Next, Then and Later. Each station holds themes, never dates.
Each Now theme links the docs page that describes it. Below the line, in page text the site search indexes, the page
links the decision log under "What bundlemcp won't do" and names GitHub Discussions (Ideas) under "Have a say".

#### Scenario: The roadmap is in the navigation
- **WHEN** a visitor opens any page of the built site
- **THEN** the top navigation links `/roadmap`, and that page shows the five stations in order, each with at least one
  theme or, for In progress, the empty-state line

#### Scenario: No dates on the roadmap
- **WHEN** the roadmap page is built
- **THEN** no station or theme names a calendar date, month or quarter

#### Scenario: Now themes link their docs
- **WHEN** a visitor clicks a theme of the Now station
- **THEN** it opens the docs page that describes that theme, and the build reports no dead link

#### Scenario: Won't-do and Have-a-say are searchable
- **WHEN** a visitor searches the site for "won't do"
- **THEN** the roadmap page is among the results, and its "What bundlemcp won't do" section links the decision log

#### Scenario: Discussions follow repository visibility
- **WHEN** the site is built without the repository declared public
- **THEN** "Have a say" names GitHub Discussions as plain text, with no link into the repository

### Requirement: DOC-17 In-progress station from open changes
The In progress station MUST be generated when the site is built, from the changes that are not archived in
`openspec/changes/`. Each change shows its name, the first sentence of its proposal's "Why" and how many of its tasks
are checked out of all of them. A change links its proposal only when the site is built with the repository declared
public. With no active change, the station says that nothing is in flight.

#### Scenario: An active change appears
- **GIVEN** `openspec/changes/<change>/` holds a proposal and a task list with 3 of 8 tasks checked
- **WHEN** the site is built
- **THEN** the In progress station shows the change's name, the first sentence of its proposal's "Why" and "3/8"

#### Scenario: An archived change does not appear
- **WHEN** a change is moved to `openspec/changes/archive/` and the site is rebuilt
- **THEN** the In progress station no longer shows it

#### Scenario: Nothing in flight
- **GIVEN** `openspec/changes/` holds no change outside `archive/`
- **WHEN** the site is built
- **THEN** the In progress station says that nothing is in flight

#### Scenario: A private build links no proposal
- **WHEN** the site is built without the repository declared public
- **THEN** each In progress entry is plain text, with no link into the repository
