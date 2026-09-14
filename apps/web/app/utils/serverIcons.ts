/** Icons and labels that make a server's kind recognisable at a glance. */

/** How the gateway authenticates to the server. */
export const AUTH_MODE_ICON: Record<string, string> = {
  none: "i-lucide-lock-open",
  static_headers: "i-lucide-key-round",
  upstream_oauth: "i-lucide-shield-check",
};
export const AUTH_MODE_LABEL: Record<string, string> = {
  none: "no auth",
  static_headers: "API key / headers",
  upstream_oauth: "OAuth",
};
export const AUTH_MODE_HELP: Record<string, string> = {
  none: "The server accepts requests without a credential",
  static_headers: "A fixed credential is sent on every request, such as an API key header",
  upstream_oauth: "The gateway holds OAuth tokens obtained from the server's authorization server",
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
