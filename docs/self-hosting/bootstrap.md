# Bootstrap file

A bootstrap document declares upstream servers, bundles and endpoints that the gateway applies **at startup**, as
upserts by name. Applying the same document twice changes nothing, so it is the natural way to provision a gateway from
CI, a compose file or a secret store without clicking through the UI.

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
four lists: `upstreams`, `bundles`, `endpoints` and `api_keys` ([API keys](#api-keys)).

```yaml
version: 1

upstreams:
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
    upstreams:
      - weather
      - notes
    resources:                          # documents the bundle serves itself
      - name: guides/planning
        title: How we plan a week
        content: |
          # Planning
          Check the forecast before suggesting outdoor plans.
    prompts:                            # resources first: a prompt may embed one
      - name: plan-week
        description: Plan the coming week
        arguments:
          - name: city
            required: true
        messages:
          - role: user
            text: "Plan my week in {{city}}."
          - role: user
            resource: guides/planning

endpoints:
  - name: assistant
    bundle_name: assistant
    profile: oauth_only
    auth_modes: [oauth]

  - name: assistant-scripts
    bundle_name: assistant
    profile: default
    auth_modes: [api_key]
    rate_limit:
      per_client:
        limit: 600
        window_seconds: 60

  - name: assistant-web
    bundle_name: assistant
    auth_modes: [none]
    allow_unauthenticated: true
    allowed_origins: ["https://app.example"]   # only this site's pages, from a browser
```

The entries use exactly the same schemas as the management API's `PUT` routes:

| List | Schema | Notes |
|---|---|---|
| `upstreams` | the upstream server upsert body plus an optional `upstream_oauth` block | See [Upstream servers](/manage/servers) for every field. `upstream_oauth` is the pre-registered client the gateway presents to an OAuth-protected server (`client_id`, and optionally `client_secret`, `authorization_url`, `token_url`, `grant_type`), as the server's upstream OAuth client route takes it. It needs token encryption keys; without them the document does not apply. |
| `bundles` | the bundle upsert body plus `upstreams`, a list of member names, and `prompts` and `resources`, lists of the bundle's own prompt and resource upsert bodies | Members are added with `enabled: true`. Prompts and resources are created or replaced by name; resources are applied first, so a prompt can embed one. See [the bundle's own prompts and documents](/manage/bundles#bundle-prompts-and-documents). Tool-level curation is not part of the document; set it through the API afterwards. |
| `endpoints` | the endpoint upsert body | Profile and auth-mode rules are validated as on the API. |

An unknown key, in the document or in a bundle entry, makes the document invalid instead of being ignored, so a typo
fails at startup rather than quietly leaving something out.

## Semantics

- **Upsert by name.** An existing server, bundle or endpoint with the same name is updated to match; a missing one is
  created. Nothing is deleted: resources absent from the document are left alone.
- **Ordinary resources afterwards.** Anything bootstrap created can be edited in the UI. The next startup writes the
  document's values again, so keep the document the source of truth for the fields it names, or drop the resource from
  it.
- **Secrets stay out of the repo.** `static_headers` values and upstream OAuth client secrets are real credentials.
  Template them in from your secret store before the file reaches the container, or supply the whole document through
  `BUNDLEMCP_BOOTSTRAP` from a secret.
- **Tools are discovered, without blocking startup.** Once the document has landed, every server it creates is probed
  in the background, as after creating it through the API, so a fresh gateway lists its tools without a manual
  `:refresh-tools`. On later starts a server is probed again only if the document changed how it is reached (URL,
  headers, auth or identity settings, protocol mode) or its last probe failed, so a restart does not wake idle
  upstreams. A server that is not up yet keeps its failure in `connection_state` and is probed again by the
  periodic refresh (`BUNDLEMCP_DISCOVERY_REFRESH_INTERVAL`) or an explicit refresh; a failed probe never fails the
  bootstrap.

## API keys

The document can provision API keys, without ever holding a key value. Each entry under `api_keys` names a key, its
kind and, for an `endpoint` key, the endpoints it may call by name (none means every endpoint). Its value comes from
one of two places:

```yaml
api_keys:
  - name: registrar
    kind: service
    value_from_env: REGISTRAR_KEY      # a bmcp_sk_… value you generated and supply out of band
  - name: ci
    kind: endpoint
    endpoints: [demo]
    create_if_missing: true
    write_to: /run/bundlemcp/ci.key    # the gateway generates the value and writes it here
```

- **`value_from_env`** names an environment variable holding a `bmcp_sk_…` value. An unset variable, or one holding
  anything else, fails the document; the error names the variable, never its value.
- **`create_if_missing`** generates the value on the first boot that finds no key of that name, and writes it to
  `write_to`, created with mode `0600`. The value appears in no log line. The file is never overwritten: when it
  already holds a `bmcp_sk_…` value — the database was reset, the file kept — that value is used, and any other
  existing file fails the document. Mount the directory from somewhere only the operator reads.

A key is matched by its name, and key names are unique. A key whose name already exists is never overwritten,
re-scoped or re-activated by the document: deactivate or delete it through the API, and the document leaves that
alone. Keys are applied after endpoints, so a scope may name an endpoint the same document defines; an endpoint
neither the document nor the store defines fails the document.

`BUNDLEMCP_INITIAL_SERVICE_KEY` still works beside the document: the gateway stores its hash the first time it
starts with no service key present, and ignores the variable from then on.

## The demo seed

`deploy/seed.yaml` is the document the reference stack applies. It registers the `echo` example server and `oauth-demo`,
an upstream that is itself OAuth-protected (`examples/oauth-demo-mcp`, login `demo_user` / `demo_password`), bundles
both as `demo`, and exposes the bundle at three endpoints: `demo` with API-key access, and `claude` and `chatgpt` with
OAuth for those clients, using the `oauth_only` and `write_as_read` profiles. It also registers the maintainers' fleet
of upstream servers behind the `fleet` compose profile. Copy it as a starting point and remove the fleet entries.
