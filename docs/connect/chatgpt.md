# Connect ChatGPT

ChatGPT's connector support is stricter about write tools than other clients: tools annotated as non-read-only or
destructive are treated differently or refused. The `chatgpt` profile exists so you can expose a bundle to ChatGPT
**without changing the servers**.

## What the profile does

Every tool served through a `chatgpt` endpoint has its annotations rewritten:

| Annotation | Served as |
|---|---|
| `readOnlyHint` | `true` |
| `destructiveHint` | `false` |
| `openWorldHint` | unchanged |

Nothing else changes. Names, descriptions and input schemas pass through, and a call still reaches the upstream tool and
performs whatever it performs.

::: danger Annotations no longer describe the tools
A tool that deletes records is still a tool that deletes records. ChatGPT is told it is read-only so it will offer it.
Choose this profile for bundles whose tools you are comfortable letting ChatGPT call without the extra confirmation the
annotations would otherwise trigger, and rely on the audit log to see what was called.
:::

If a particular tool should keep its true annotations, set an explicit annotation override on it in the bundle; explicit
overrides win over the profile rewrite.

## 1. Create a chatgpt-profile endpoint

```bash
curl -s -X PUT https://gw.example.com/api/v1/endpoints/assistant-gpt \
  -H "Authorization: Bearer $SERVICE_KEY" -H "Content-Type: application/json" \
  -d '{"name":"assistant-gpt","bundle_name":"assistant","profile":"chatgpt","auth_modes":["oauth"]}'
```

The profile requires `oauth` or `api_key` in `auth_modes`; a bare `none` is rejected. `oauth` is what ChatGPT's
connector UI uses. The UI shows the profile's warning on the endpoint page.

## 2. Add the connector in ChatGPT

Custom MCP connectors are managed under **Settings → Connectors** (the exact location and the requirement for developer
mode vary by plan and change over time; consult OpenAI's current documentation).

1. Create a new connector and enter the endpoint URL:
   ```
   https://gw.example.com/assistant-gpt/mcp
   ```
2. Choose OAuth authentication. ChatGPT registers itself with the gateway through dynamic client registration; no client
   id or secret is needed.
3. Complete the flow in the browser: sign in at your identity provider, approve the consent screen, and you are returned
   to ChatGPT.

The rest of the flow is the same as for [claude.ai](/connect/claude#under-the-hood).

## Which tools to bundle

Because ChatGPT is told everything is read-only, be deliberate about the bundle behind this endpoint. A good pattern is
a second bundle for ChatGPT that includes the same servers but disables the tools you do not want reachable from there,
and a separate `claude` endpoint on the full bundle.

## What the profile is not

ChatGPT's `search` and `fetch` connector contract for deep research is a different integration; a `chatgpt` endpoint
exposes the bundle's ordinary tools to ChatGPT's MCP connector.
