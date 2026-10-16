## MODIFIED Requirements

### Requirement: BND-32 Bootstrap carries prompts and resources
Bootstrap ([management](../management/spec.md)) and export/import
([management](../management/spec.md)) MUST carry each bundle's prompts and resources inside the bundle entry,
upserted by natural key. An entry absent from the document is not deleted; import keeps
[MGMT-20](../management/spec.md), so it deletes nothing unless a future `prune=true` says so.

#### Scenario: Bootstrap applies resources before the prompts that embed them
- **GIVEN** a bootstrap document whose bundle entry has a prompt embedding a resource defined in the same entry
- **WHEN** bootstrap runs
- **THEN** both are stored and the prompt's reference is valid

#### Scenario: Export carries a bundle's prompts and resources
- **GIVEN** bundle `b1` with prompt `triage` and resource `handbook`
- **WHEN** `GET /api/v1/export` is called
- **THEN** `b1`'s entry lists `triage` under `prompts` and `handbook` under `resources`, with their full content

#### Scenario: Import keeps prompts the document does not list
- **GIVEN** bundle `b1` on the target has prompt `local-only`, which the imported document's `b1` entry does not list
- **WHEN** the document is imported
- **THEN** `local-only` still exists

### Requirement: BND-10 Name is the natural key
Bundle `name` MUST be the natural key for bootstrap upserts ([MGMT-9](../management/spec.md)) and for
export and import ([MGMT-17](../management/spec.md), [MGMT-19](../management/spec.md)): a bundle is created or
updated by its name, and an imported entry whose name matches no bundle creates a new one. The name in the path and
body of `PUT /api/v1/bundles/{name}` must agree, so a different name is a different bundle. A bundle is renamed only by
the explicit action `POST /api/v1/bundles/{name}:rename?new_name=…`, which keeps its id, members, curation, prompts,
resources and endpoints. Because automation keyed on the old name — a bootstrap file, an exported document — would
then create a new bundle under that name, the action MUST refuse with `409` stating that consequence unless
`force=true` acknowledges it, and the admin UI MUST show the warning and require the acknowledgement before renaming.

#### Scenario: Upsert by name updates in place
- **WHEN** `PUT /api/v1/bundles/b1` is called twice with different descriptions
- **THEN** one bundle `b1` exists, carrying the second description

#### Scenario: Import matches bundles by name
- **GIVEN** the target has bundle `b1` and the imported document lists bundles `b1` and `b2`
- **WHEN** the document is imported
- **THEN** `b1` is updated in place and `b2` is created

#### Scenario: Rename without acknowledgement is refused
- **WHEN** `POST /api/v1/bundles/b1:rename?new_name=b2` is called without `force`
- **THEN** the response is `409` saying a document keyed on `b1` would create a new bundle, and nothing is renamed

#### Scenario: Acknowledged rename keeps the bundle
- **GIVEN** bundle `b1` with a member, a curated tool and endpoint `b1-api`
- **WHEN** `POST /api/v1/bundles/b1:rename?new_name=b2&force=true` is called
- **THEN** bundle `b2` has that member and curation, endpoint `b1-api` serves `b2`, and no bundle `b1` exists

#### Scenario: Rename to a taken name is refused
- **WHEN** a bundle is renamed to the name another bundle already has
- **THEN** the response is `409` and neither bundle changes
