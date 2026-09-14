/** Icons that make an endpoint's client profile and auth modes recognisable at a glance. */

export const PROFILE_ICON: Record<string, string> = {
  default: "i-lucide-plug",
  claude: "i-lucide-sparkles",
  chatgpt: "i-lucide-message-square",
};
export const PROFILE_HELP: Record<string, string> = {
  default: "Passthrough for any MCP client",
  claude: "Shaped for claude.ai: OAuth only, tools passed through",
  chatgpt: "Shaped for ChatGPT: every tool presented as read-only",
};

export const ENDPOINT_AUTH_ICON: Record<string, string> = {
  oauth: "i-lucide-shield-check",
  api_key: "i-lucide-key-round",
  none: "i-lucide-lock-open",
};
export const ENDPOINT_AUTH_HELP: Record<string, string> = {
  oauth: "Callers sign in through the gateway's OAuth server (people and their MCP clients)",
  api_key: "Callers present an endpoint API key (scripts, agents, automation)",
  none: "Open: anyone who knows the URL",
};
