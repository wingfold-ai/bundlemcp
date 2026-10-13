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
updated by its name, and an imported entry whose name matches no bundle creates a new one. The API offers no rename for
a bundle; the name in the path and body of `PUT /api/v1/bundles/{name}` must agree, so a different name is a different
bundle.

#### Scenario: Upsert by name updates in place
- **WHEN** `PUT /api/v1/bundles/b1` is called twice with different descriptions
- **THEN** one bundle `b1` exists, carrying the second description

#### Scenario: Import matches bundles by name
- **GIVEN** the target has bundle `b1` and the imported document lists bundles `b1` and `b2`
- **WHEN** the document is imported
- **THEN** `b1` is updated in place and `b2` is created
