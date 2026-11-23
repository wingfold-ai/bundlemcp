---
description: "Export the whole bundlemcp configuration as one JSON document and import it elsewhere, for backups,
  moves to production or a first bootstrap file."
---

# Export and import

The whole configuration — upstream servers, bundles with their members, curation, prompts and resources, and
endpoints — can be taken out as one JSON document and applied to the same or another gateway. Use it for backups,
to move a setup from staging to production, or to write the first [bootstrap file](/self-hosting/bootstrap): an
export *is* a bootstrap document, and any bootstrap document can be imported.

Users, the gateway's own OAuth state (clients, codes, tokens, consents), API keys, audit records and the upstream
tokens users connected are never exported, and an import never creates them. They are identity and runtime state,
not configuration.

## Exporting

```bash
curl -s https://gw.example.com/api/v1/export -H "Authorization: Bearer $SERVICE_KEY" > bundlemcp.json
```

Every resource is identified by its name, never by a database id, so the document means the same thing on another
gateway. A bundle's members are listed first member first, each with its enable flag and the curation of its tools,
the tools named as their upstream names them:

```json
{
  "version": 1,
  "upstreams": [
    {
      "name": "weather",
      "url": "http://weather-mcp:8080/mcp",
      "static_headers": { "Authorization": { "$secret": "Authorization" } },
      "upstream_oauth": { "client_id": "gw", "client_secret": { "$secret": "client_secret" } }
    }
  ],
  "bundles": [
    {
      "name": "assistant",
      "upstreams": [
        { "name": "weather", "enabled": true, "tools": [{ "tool": "forecast", "override_title": "Forecast" }] }
      ],
      "resources": [],
      "prompts": []
    }
  ],
  "endpoints": [{ "name": "assistant", "bundle_name": "assistant", "auth_modes": ["oauth"] }]
}
```

### Secrets

Header values and upstream OAuth client secrets are written as **placeholders**, `{"$secret": "<name>"}`. On import
a placeholder keeps the value the target already stores under that name; a target that stores none reports that
upstream as an error and imports nothing. To move secrets too, put the values into the document yourself, or take a
full backup with the values:

```bash
curl -s "https://gw.example.com/api/v1/export?include_secrets=true" -b "bmcp_session=…"
```

`include_secrets=true` needs an administrator's browser session; a service key gets `403`, so automation cannot take
secrets out. Such an export carries a `warning` field saying the document holds credentials, and writes an audit
record of kind `management` with action `export.secrets_included`, the admin and the time
([Audit log](/manage/audit)). Treat the file as you would a password.

## Importing

```bash
curl -s -X POST "https://gw.example.com/api/v1/import?dry_run=true" \
  -H "Authorization: Bearer $SERVICE_KEY" -H "Content-Type: application/json" --data @bundlemcp.json
```

An import applies the document as upserts by name, through the same rules as the management API, and answers with
one result per resource: `created`, `updated`, `skipped` (nothing would change) or `error` with a message. The
document lands entirely or not at all: if any resource errors, nothing is written. `dry_run=true` reports the same
results and writes nothing, so preview first and apply when the report reads right.

- **Nothing is deleted.** A resource the document does not list, and a prompt or resource a bundle entry omits, are
  left as they are.
- **Curation needs discovered tools.** A tool's curation is matched to the target's discovered tool of that name. On a
  fresh gateway the upstreams have not been probed yet, so those entries are reported `skipped` with "tool not
  discovered yet; re-import after discovery". Import once, let discovery run (a few seconds), and import the same
  document again; importing is idempotent.
- **Large documents.** The management API refuses bodies over `max_request_bytes` (4 MiB by default). A document
  with several large bundle resources can exceed it: raise that runtime setting first, or import bundle by bundle.
- Only `version: 1` exists; any other version is refused with `422`.

In the admin UI, **Settings → Export and import** downloads an export, and an import first shows the dry-run report
and writes only when you confirm it.

## Renaming a bundle

Bundles are matched by name. After a bundle is renamed, a document that still names the old bundle creates a new one
under the old name; the rename action warns about this and needs `force=true` — see
[Bundles](/manage/bundles).
