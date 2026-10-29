/** Icons and labels that make a server's kind recognisable at a glance. */
import type { components } from "~~/types/api";

/** How the gateway authenticates to the server. */
export const AUTH_MODE_ICON: Record<string, string> = {
  none: "i-lucide-lock-open",
  static_headers: "i-lucide-key-round",
  upstream_oauth: "i-lucide-shield-check",
  delegated_token: "i-lucide-ticket",
};
export const AUTH_MODE_LABEL: Record<string, string> = {
  none: "no auth",
  static_headers: "API key / headers",
  upstream_oauth: "OAuth",
  delegated_token: "delegated token",
};
export const AUTH_MODE_HELP: Record<string, string> = {
  none: "The server accepts requests without a credential",
  static_headers: "A fixed credential is sent on every request, such as an API key header",
  upstream_oauth: "The gateway holds OAuth tokens obtained from the server's authorization server",
  delegated_token:
    "Each call carries a short-lived token the gateway issues for the caller, valid only at " +
    "this server; the server verifies it through the gateway's introspection endpoint",
};

/** Whose upstream identity a call carries: one account an admin connected, or the caller's own. */
export const IDENTITY_MODE_ICON: Record<string, string> = {
  shared: "i-lucide-user-cog",
  per_user: "i-lucide-users",
};
export const IDENTITY_MODE_LABEL: Record<string, string> = {
  shared: "admin account",
  per_user: "per user",
};
export const IDENTITY_MODE_HELP: Record<string, string> = {
  shared: "Every caller uses the one account an admin connected",
  per_user: "Each caller connects their own account and the upstream sees them as themselves",
};

/** Where the server sits, see connectionKind(). */
export const NETWORK_ICON: Record<string, string> = {
  local: "i-lucide-network",
  external: "i-lucide-globe",
};

export const HEALTH_ICON: Record<string, string> = {
  ok: "i-lucide-circle-check",
  error: "i-lucide-circle-x",
  unknown: "i-lucide-circle-help",
};

/** What the last probe found out about the upstream. */
export const CONNECTION_STATE_LABEL: Record<string, string> = {
  unknown: "not probed",
  ready: "ready",
  oauth_required: "needs OAuth sign-in",
  account_required: "account not connected",
  insufficient_scope: "needs more permission",
  credential_required: "needs a credential",
  not_mcp: "not an MCP endpoint",
  unreachable: "unreachable",
  egress_denied: "blocked by egress policy",
  error: "error",
};
export const CONNECTION_STATE_ICON: Record<string, string> = {
  unknown: "i-lucide-circle-help",
  ready: "i-lucide-plug-zap",
  oauth_required: "i-lucide-shield-alert",
  account_required: "i-lucide-user-round-x",
  insufficient_scope: "i-lucide-shield-minus",
  credential_required: "i-lucide-key-round",
  not_mcp: "i-lucide-file-question",
  unreachable: "i-lucide-unplug",
  egress_denied: "i-lucide-ban",
  error: "i-lucide-circle-x",
};
export const CONNECTION_STATE_HELP: Record<string, string> = {
  unknown: "The server has not been probed yet",
  ready: "The server answered as an MCP server",
  oauth_required: "The server asks for OAuth sign-in",
  account_required: "Upstream OAuth is set up, but no account is connected to use it yet",
  insufficient_scope: "The connected account lacks a permission the server asked for; reconnect",
  credential_required:
    "The server refuses requests without a credential it recognises, and publishes no OAuth " +
    "metadata: it wants an API key or token header",
  not_mcp: "The URL answers, but not as a Streamable HTTP MCP endpoint",
  unreachable: "The server could not be reached: connection, TLS or timeout",
  egress_denied: "The gateway's egress policy does not allow this address",
  error: "The server answered with an error",
};

export function connectionStateColor(
  state: string,
): "success" | "warning" | "error" | "neutral" {
  if (state === "ready") return "success";
  if (["oauth_required", "account_required", "insufficient_scope", "credential_required"].includes(state))
    return "warning";
  if (state === "unknown") return "neutral";
  return "error";
}

/** The one question registration asks: where the upstream credential comes from. */
export type CredentialSource =
  | "none"
  | "key"
  | "per_user"
  | "shared_oauth"
  | "client_credentials"
  | "delegated";

export const CREDENTIAL_SOURCES: { value: CredentialSource; label: string; help: string }[] = [
  {
    value: "none",
    label: "No credential needed",
    help: "The server answers anyone who can reach it.",
  },
  {
    value: "key",
    label: "A key or token I enter",
    help:
      "Sent as a header on every request and shared by every caller. Use this for API keys " +
      "and personal access tokens.",
  },
  {
    value: "per_user",
    label: "Each user signs in with their own account",
    help:
      "OAuth. Every caller connects their own account the first time they use a tool, so the " +
      "server sees them as themselves. Only endpoints that require sign-in can offer it.",
  },
  {
    value: "shared_oauth",
    label: "One shared account I sign in with once",
    help:
      "OAuth with a single account an admin connects (a service account). Every caller acts " +
      "as that account.",
  },
  {
    value: "client_credentials",
    label: "One shared machine account (client credentials)",
    help:
      "OAuth for a server that authorizes the gateway itself: enter the client id and secret " +
      "the provider issued; no browser sign-in.",
  },
  {
    value: "delegated",
    label: "A token the gateway issues for each caller",
    help:
      "For your own servers: each call carries a short-lived token bound to this server, " +
      "which it verifies with the gateway's introspection endpoint to learn who is calling.",
  },
];

/** The auth and identity settings a credential source maps to. */
export function credentialSettings(source: CredentialSource): {
  auth_mode: components["schemas"]["ServerAuthMode"];
  identity_mode: components["schemas"]["IdentityMode"];
} {
  switch (source) {
    case "key":
      return { auth_mode: "static_headers", identity_mode: "shared" };
    case "per_user":
      return { auth_mode: "upstream_oauth", identity_mode: "per_user" };
    case "shared_oauth":
    case "client_credentials":
      return { auth_mode: "upstream_oauth", identity_mode: "shared" };
    case "delegated":
      return { auth_mode: "delegated_token", identity_mode: "shared" };
    default:
      return { auth_mode: "none", identity_mode: "shared" };
  }
}

/** Header presets for the credential most servers document. */
export const CREDENTIAL_HEADER_PRESETS: { label: string; name: string; prefix: string }[] = [
  { label: "Authorization: Bearer <token>", name: "Authorization", prefix: "Bearer " },
  { label: "X-API-Key: <key>", name: "X-API-Key", prefix: "" },
  { label: "Other header", name: "", prefix: "" },
];
