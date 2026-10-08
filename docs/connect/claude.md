# Connect claude.ai

claude.ai connects to remote MCP servers as **custom connectors** and expects the server to be an OAuth 2.1 resource
with a discoverable authorization server. bundlemcp provides all of that: an endpoint with the `claude` profile
publishes the protected-resource metadata, the gateway registers the client dynamically or via its metadata document,
runs the authorisation flow with PKCE, and shows a consent screen. Nothing needs to be configured in claude.ai beyond
the URL.

## 1. Create a claude-profile endpoint

```bash
curl -s -X PUT https://gw.example.com/api/v1/endpoints/assistant \
  -H "Authorization: Bearer $SERVICE_KEY" -H "Content-Type: application/json" \
  -d '{"name":"assistant","bundle_name":"assistant","profile":"claude","auth_modes":["oauth"]}'
```

The `claude` profile requires `auth_modes` to be exactly `["oauth"]`; the gateway rejects anything else. Tools pass
through unchanged.

In the UI: open the bundle, and in its **Endpoints** card create one with the `claude` profile. The endpoint page shows
the URL to paste into claude.ai, and every signed-in user finds the same URL in the catalogue.

## 2. Add the connector in claude.ai

1. In claude.ai open **Settings → Connectors** and choose **Add custom connector**.
2. Enter a name and the endpoint URL:
   ```
   https://gw.example.com/assistant/mcp
   ```
   Leave the client id and secret fields empty. claude.ai registers itself with the gateway.
3. Click **Connect**. Your browser is sent to the gateway.

## 3. What happens in the browser

1. The gateway needs to know who you are. If you have no session it sends you to your organisation's identity provider;
   sign in there.
2. Back at the gateway, a **consent screen** names the client (Claude), the endpoint, and the requested scope. Approve
   it.
3. You are returned to claude.ai with an authorisation code; claude.ai exchanges it for tokens and the connector shows
   as connected.

The consent is remembered per user, client and endpoint. Reconnecting later skips the screen until an admin or the user
revokes the consent.

## 4. Use the tools

Tools appear in claude.ai under the connector's name with their presented names, for example `weather__forecast` or an
override such as `get_forecast`. The bundle's description is served as the server instructions.

## Under the hood

For anyone debugging the flow, the gateway serves:

| Route | Purpose |
|---|---|
| `GET /.well-known/oauth-protected-resource/assistant/mcp` | Names the authorization server for this endpoint. Also referenced by the 401 challenge on the endpoint. |
| `GET /.well-known/oauth-authorization-server` | RFC 8414 metadata: authorize, token, registration, introspection and revocation endpoints, PKCE methods, and the `client_id_metadata_document_supported` flag. |
| `POST /oauth/register` | Dynamic client registration for clients that still use it. A public deployment serving only claude.ai can restrict it to Claude's callback with `BUNDLEMCP_DCR_ALLOWED_REDIRECT_URIS`, see [Client registration](/self-hosting/configuration#client-registration). |
| `GET /oauth/authorize` | Requires a browser session; federates to the identity provider, then consent. |
| `POST /oauth/token` | `authorization_code` and `refresh_token` grants. Access tokens live one hour by default, refresh tokens seven days and rotate on every use. |

Tokens are **bound to the endpoint** they were issued for (RFC 8707 `resource`). A token for `assistant` is refused at
`assistant-gpt`, and the client re-authorises there. Every authorisation response carries `iss` so a client can detect a
mix-up between authorization servers.

The full model — how this flow relates to the identity provider and to API keys, and what the upstream server sees — is
in
[Authentication](/guide/authentication).

## Troubleshooting

**"Connection failed" right after entering the URL.** claude.ai fetched the protected-resource metadata and did not get
what it expected. Check that `BUNDLEMCP_PUBLIC_URL` is exactly the URL you typed, that the endpoint is enabled, and that
the profile is `claude`.

**The browser lands on the identity provider and errors.** The redirect URI `<public url>/login/callback` is not
registered with the provider, or the provider's discovery URL is blocked by the egress policy. See
[Identity provider](/self-hosting/identity-provider).

**Connected, but the user has no tools.** The bundle has no enabled members, or every tool is disabled. Check the bundle
page.

**A user must reconnect after a rollout.** Their refresh token expired, or an admin revoked their consent. Reconnecting
is a one-click flow; the consent screen only reappears if the consent was revoked.

**Several users need to connect their own accounts to an upstream.** Mark that server `identity_mode: per_user`; each
user is sent a connect link on their first call. See [Servers](/manage/servers#shared-versus-per-user-identity).
