# Bootstrap file

A bootstrap document declares servers, bundles and endpoints that the gateway applies **at startup**, as upserts by
name. Applying the same document twice changes nothing, so it is the natural way to provision a gateway from CI, a
compose file or a secret store without clicking through the UI.

## Enabling it

Either mount a file and point at it:

```yaml
services:
  gateway:
    environment:
      BUNDLEMCP_BOOTSTRAP_FILE: /app/deploy/seed.yaml
      BUNDLEMCP_BOOTSTRAP_STRICT: "true"
    volumes:
      - ./seed.yaml:/app/deploy/seed.yaml:ro
```

or pass the document inline as JSON in `BUNDLEMCP_BOOTSTRAP`. When both are set, the file is applied first and the
inline document second.

With `BUNDLEMCP_BOOTSTRAP_STRICT=true` a document that fails validation or application stops the gateway from starting,
which is what you want in production and CI. The default `false` logs the failure and continues.

## Format

YAML or JSON; JSON is valid YAML so one parser serves both. The document has a `version` (currently always `1`) and
three lists.

```yaml
version: 1

servers:
  - name: weather
    description: Forecasts and current conditions
    url: http://weather-mcp:8080/mcp
    auth_mode: static_headers
    static_headers:
      authorization: Bearer ${WEATHER_TOKEN}   # substitute before mounting
    send_identity_header: true

  - name: notes
    description: Per-user notes; verifies the forwarded bearer itself
    url: http://notes-mcp:8080/mcp
    forward_headers:
      authorization: authorization

bundles:
  - name: assistant
    description: Everything a personal assistant needs
    servers:
      - weather
      - notes

endpoints:
  - name: assistant
    bundle_name: assistant
    profile: claude
    auth_modes: [oauth]

  - name: assistant-scripts
    bundle_name: assistant
    profile: default
    auth_modes: [api_key]
    rate_limit:
      per_client:
        limit: 600
        window_seconds: 60
```

The entries use exactly the same schemas as the management API's `PUT` routes:

| List | Schema | Notes |
|---|---|---|
| `servers` | the server upsert body | See [Servers](/manage/servers) for every field. |
| `bundles` | the bundle upsert body plus `servers`, a list of member names | Members are added with `enabled: true`. Tool-level curation is not part of the document; set it through the API afterwards. |
| `endpoints` | the endpoint upsert body | Profile and auth-mode rules are validated as on the API. |

## Semantics

- **Upsert by name.** An existing server, bundle or endpoint with the same name is updated to match; a missing one is
  created. Nothing is deleted: resources absent from the document are left alone.
- **Ordinary resources afterwards.** Anything bootstrap created can be edited in the UI. The next startup writes the
  document's values again, so keep the document the source of truth for the fields it names, or drop the resource from
  it.
- **Secrets stay out of the repo.** `static_headers` values and upstream OAuth client secrets are real credentials.
  Template them in from your secret store before the file reaches the container, or supply the whole document through
  `BUNDLEMCP_BOOTSTRAP` from a secret.
- **Probing does not block startup.** Servers are registered and probed; a server that is not up yet is stored with
  `health_status: error` and re-probed on the next refresh or the next live call.

## API keys

The document does not carry API keys. For a headless first boot, set `BUNDLEMCP_INITIAL_SERVICE_KEY` to a value you
generated; the gateway stores its hash the first time it starts with no service key present, and ignores the variable
from then on. Create further keys through the API with that key, then retire it.

## The demo seed

`deploy/seed.yaml` is the document the reference stack applies. It registers the `echo` example server, bundles it as
`demo` and exposes it at the `demo` endpoint with API-key access, plus the maintainers' fleet of upstream servers behind
the `fleet` compose profile. Copy it as a starting point and remove the fleet entries.
