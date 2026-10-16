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
- A key is matched by name; an existing key is never overwritten, re-scoped or re-activated by the document.
- `BUNDLEMCP_INITIAL_SERVICE_KEY` keeps working exactly as today; ADR-0013 calls it "the MGMT-10 pattern", and it stays
  part of MGMT-10.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `management`: MGMT-8 (the document carries API keys), MGMT-10 (renamed to *API keys at bootstrap*: referenced or
  generated keys from the document, alongside the initial service key; existing keys never overwritten).

## Open decision

- **Printing a generated key to the startup log.** The original MGMT-10 prints a `create_if_missing` key's value once to
  the startup log, but OPS-8 and SEC-10 say a secret never appears in logs. The delta here keeps the original wording.
  Alternatives the maintainers choose between before applying:
  1. Build it as written, and carve a one-time exception into SEC-10 and OPS-8 (both are modified by other changes —
     [add-prometheus-metrics](../add-prometheus-metrics/proposal.md) and
     [improve-request-observability](../archive/2026-10-16-improve-request-observability/proposal.md) — so the exception
     lands in whichever of them is applied later).
  2. Write the generated value to an operator-named file (created `0600`, never overwritten) instead of the log.
  3. Drop `create_if_missing` and support only environment references.
- **Natural key.** API key names are not unique today. The delta matches entries by name and treats any existing key
  with that name as present. Alternative: make key names unique (a migration and a 409 on the create route).

## Impact

- **Code:** `application/bootstrap/` (a new document entry, applied by `BootstrapRunner` after endpoints so scopes
  resolve by name, inside the document's transaction), `application/management/api_key_service.py` (create from a
  supplied value, find by name), and the settings documentation for any new variable.
- **Depends on** nothing; the export format of [add-export-import](../add-export-import/proposal.md) shares the
  document's schema but never carries API keys (keys are not exportable — only their hashes are stored).
- **Docs:** `docs/self-hosting/bootstrap.md` (its *API keys* section says the document carries none), and
  `deploy/.env.example` / `deploy/seed.yaml` if the demo uses the feature.
- **ADR:** none new; ADR-0013 is append-only and stays as written.
