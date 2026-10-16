# Proposal: API keys in the bootstrap document

## Why

The bootstrap document provisions upstreams, bundles and endpoints, but not API keys: the only headless key is the one
service key from `BUNDLEMCP_INITIAL_SERVICE_KEY`. A deployment that wants, say, a registrar's service key and a CI
endpoint key scoped to one endpoint still needs API calls after the first boot. The original bootstrap spec had the
document carry API keys — by reference to a value supplied out of band, or generated on first boot — and that half was
never built.

## What Changes

- The bootstrap document gains an `api_keys` list (MGMT-8). Each entry names the key, its kind and, for an
  endpoint-kind key, the endpoints it is scoped to by name.
- An entry supplies its value in one of two ways (MGMT-10): a reference to an environment variable holding the value —
  the document itself never contains a key value — or `create_if_missing`, where the gateway generates the value and
  prints it once to the startup log.
- A key is matched by name, and names become unique (AUTH-23); an existing key is never overwritten, re-scoped or
  re-activated by the document.
- `BUNDLEMCP_INITIAL_SERVICE_KEY` keeps working exactly as today; ADR-0013 calls it "the MGMT-10 pattern", and it stays
  part of MGMT-10.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `auth`: AUTH-23 (key names are unique; a duplicate create answers 409).
- `management`: MGMT-8 (the document carries API keys), MGMT-10 (renamed to *API keys at bootstrap*: referenced or
  generated keys from the document, alongside the initial service key; existing keys never overwritten).

## Decisions

- **A generated key goes to a file, never to the log.** A `create_if_missing` entry names the file the gateway writes
  the generated value to, created with mode `0600` and never overwritten; when that file already holds a well-formed
  value (the store was reset, the file kept), that value is used instead of a new one. SEC-10 and OPS-8 stay as they
  are: no secret appears in any log line.
- **API key names are unique.** A key is the document's entry of the same name; the create route answers 409 for a
  name already taken (AUTH-23), and a migration renames existing duplicates before adding the unique constraint.

## Impact

- **Migration:** a unique constraint on `api_keys.name`, after renaming existing duplicates
  (`<name>-<first 8 characters of its id>`).
- **Code:** `application/bootstrap/` (a new document entry, applied by `BootstrapRunner` after endpoints so scopes
  resolve by name, inside the document's transaction), `application/management/api_key_service.py` (create from a
  supplied value, find by name), and the settings documentation for any new variable.
- **Depends on** nothing; the export format of [add-export-import](../add-export-import/proposal.md) shares the
  document's schema but never carries API keys (keys are not exportable — only their hashes are stored).
- **Docs:** `docs/self-hosting/bootstrap.md` (its *API keys* section says the document carries none), and
  `deploy/.env.example` / `deploy/seed.yaml` if the demo uses the feature.
- **ADR:** none new; ADR-0013 is append-only and stays as written.
