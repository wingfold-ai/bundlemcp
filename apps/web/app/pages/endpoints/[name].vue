<script setup lang="ts">
import type { components } from "~~/types/api";

type EndpointRead = components["schemas"]["EndpointRead"];
type BundleRead = components["schemas"]["BundleRead"];
type EndpointProfile = components["schemas"]["EndpointProfile"];
type EndpointAuthMode = components["schemas"]["EndpointAuthMode"];
type RateLimitConfig = components["schemas"]["RateLimitConfig"];

interface ProfileInfo {
  name?: string;
  description?: string;
  warning?: string;
  [key: string]: unknown;
}

definePageMeta({ key: (route) => route.fullPath });

const api = useApi();
const route = useRoute();
const name = route.params.name as string;

const endpoint = ref<EndpointRead | null>(null);
const bundles = ref<BundleRead[]>([]);
const profiles = ref<ProfileInfo[]>([]);
const errorMsg = ref("");

// --- config form state ---
const profile = ref<EndpointProfile>("default");
const authModes = ref<EndpointAuthMode[]>([]);
const enabled = ref(true);
// Bound to <input type="number">, for which Vue's v-model assigns a number (or
// "" when the field is cleared) — never assume these hold a string.
const rlEndpointLimit = ref<string | number>("");
const rlEndpointWindow = ref<string | number>("");
const rlClientLimit = ref<string | number>("");
const rlClientWindow = ref<string | number>("");

async function load() {
  const [ep, bds, profs] = await Promise.all([
    api.GET("/api/v1/endpoints/{name}", { params: { path: { name } } }),
    api.GET("/api/v1/bundles", { params: { query: { offset: 0, limit: 100 } } }),
    api.GET("/api/v1/endpoints/profiles"),
  ]);
  if (ep.error) {
    errorMsg.value = apiErrorMessage(ep.error);
    return;
  }
  endpoint.value = ep.data ?? null;
  bundles.value = bds.data?.items ?? [];
  profiles.value = (profs.data ?? []) as ProfileInfo[];
  if (endpoint.value) {
    profile.value = endpoint.value.profile as EndpointProfile;
    authModes.value = endpoint.value.auth_modes as EndpointAuthMode[];
    enabled.value = endpoint.value.enabled;
    const rl = endpoint.value.rate_limit as {
      endpoint?: { limit?: number; window_seconds?: number } | null;
      per_client?: { limit?: number; window_seconds?: number } | null;
    } | null;
    rlEndpointLimit.value = rl?.endpoint?.limit != null ? String(rl.endpoint.limit) : "";
    rlEndpointWindow.value =
      rl?.endpoint?.window_seconds != null ? String(rl.endpoint.window_seconds) : "";
    rlClientLimit.value = rl?.per_client?.limit != null ? String(rl.per_client.limit) : "";
    rlClientWindow.value =
      rl?.per_client?.window_seconds != null ? String(rl.per_client.window_seconds) : "";
  }
}
await load();

const connectionUrl = computed(() => `${apiBase()}/${name}/mcp`);

const bundleName = computed(
  () => bundles.value.find((b) => b.id === endpoint.value?.bundle_id)?.name ?? "",
);

const chatgptWarning = computed(() => {
  if (profile.value !== "chatgpt") return "";
  return (
    (profiles.value.find((p) => p.name === "chatgpt")?.warning as string | undefined) ??
    "ChatGPT profile re-annotates all tools; verify tool behavior before exposing this endpoint."
  );
});

async function copyUrl() {
  await navigator.clipboard.writeText(connectionUrl.value);
}

function toggleAuthMode(mode: EndpointAuthMode, checked: boolean) {
  if (checked) {
    // Client-side rule: "none" only alone.
    if (mode === "none") {
      authModes.value = ["none"];
    } else {
      authModes.value = [...authModes.value.filter((m) => m !== "none" && m !== mode), mode];
    }
  } else {
    authModes.value = authModes.value.filter((m) => m !== mode);
  }
}

// v-model on a number input yields a number, so normalize before trimming —
// calling .trim() on it would throw and abort the whole save.
function fieldText(value: string | number): string {
  return String(value ?? "").trim();
}

function buildRateLimit(): RateLimitConfig | undefined {
  const el = fieldText(rlEndpointLimit.value);
  const ew = fieldText(rlEndpointWindow.value);
  const cl = fieldText(rlClientLimit.value);
  const cw = fieldText(rlClientWindow.value);
  if (!el && !ew && !cl && !cw) return undefined;
  return {
    endpoint: el && ew ? { limit: Number(el), window_seconds: Number(ew) } : null,
    per_client: cl && cw ? { limit: Number(cl), window_seconds: Number(cw) } : null,
  } as RateLimitConfig;
}

async function saveEndpoint() {
  errorMsg.value = "";
  if (!bundleName.value) {
    errorMsg.value = "Could not resolve bundle name for this endpoint";
    return;
  }
  if (authModes.value.length === 0) {
    errorMsg.value = "Select at least one auth mode";
    return;
  }
  if (authModes.value.includes("none") && authModes.value.length > 1) {
    errorMsg.value = 'Auth mode "none" cannot be combined with other modes';
    return;
  }
  const rateLimit = buildRateLimit();
  const { error } = await api.PUT("/api/v1/endpoints/{name}", {
    params: { path: { name } },
    body: {
      name,
      bundle_name: bundleName.value,
      profile: profile.value,
      auth_modes: authModes.value,
      allow_unauthenticated: authModes.value.includes("none"),
      enabled: enabled.value,
      ...(rateLimit !== undefined ? { rate_limit: rateLimit } : {}),
    },
  });
  if (error) {
    errorMsg.value = apiErrorMessage(error);
    return;
  }
  await load();
}

// --- danger zone ---
const renameInput = ref("");
const renameForce = ref(false);

async function renameEndpoint() {
  errorMsg.value = "";
  if (!NAME_RE.test(renameInput.value)) {
    errorMsg.value = "New name must match ^[a-zA-Z0-9_-]+$";
    return;
  }
  if (RESERVED_ENDPOINT_NAMES.includes(renameInput.value)) {
    errorMsg.value = `Name "${renameInput.value}" is reserved`;
    return;
  }
  const { error } = await api.POST("/api/v1/endpoints/{name}:rename", {
    params: { path: { name }, query: { new_name: renameInput.value, force: renameForce.value } },
  });
  if (error) {
    errorMsg.value = apiErrorMessage(error);
    return;
  }
  await navigateTo(`/endpoints/${renameInput.value}`);
}

async function deleteEndpoint() {
  if (!confirm(`Delete endpoint "${name}"?`)) return;
  const { error } = await api.DELETE("/api/v1/endpoints/{name}", {
    params: { path: { name } },
  });
  if (error) {
    errorMsg.value = apiErrorMessage(error);
    return;
  }
  await navigateTo("/endpoints");
}
</script>

<template>
  <div class="space-y-6">
    <h1 class="text-lg font-semibold">Endpoint: {{ name }}</h1>

    <p v-if="errorMsg" class="text-red-600 text-sm" data-testid="error">{{ errorMsg }}</p>

    <!-- connection instructions -->
    <div class="wf-card space-y-3">
      <h2 class="font-medium">Connection</h2>
      <div class="flex items-center gap-2">
        <code
          class="text-sm bg-elevated rounded px-2 py-1"
          data-testid="connection-url"
          >{{ connectionUrl }}</code
        >
        <UButton size="sm" variant="outline" data-testid="copy-url" @click="copyUrl">
          Copy
        </UButton>
      </div>
      <div class="text-sm text-toned space-y-3" data-testid="setup-instructions">
        <div>
          <p class="font-medium">claude.ai (custom connector)</p>
          <p>
            In claude.ai, go to Settings → Connectors → Add custom connector, paste the URL
            above, and complete the OAuth flow when prompted. Requires the "oauth" auth mode to
            be enabled on this endpoint.
          </p>
        </div>
        <div>
          <p class="font-medium">Generic API-key client</p>
          <p>
            Create an API key on the API keys page, then send it as a Bearer token. Example
            initialize request:
          </p>
          <pre class="bg-elevated rounded p-2 mt-1 overflow-x-auto text-xs">curl -X POST {{ connectionUrl }} \
  -H "Authorization: Bearer &lt;api key&gt;" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"curl","version":"0"}}}'</pre>
          <p class="mt-1">Requires the "api_key" auth mode to be enabled on this endpoint.</p>
        </div>
      </div>
    </div>

    <!-- config -->
    <div class="wf-card space-y-3">
      <h2 class="font-medium">Configuration</h2>
      <div>
        <label class="wf-label">Profile</label>
        <select v-model="profile" class="wf-input" data-testid="input-profile">
          <option v-for="p in profiles" :key="String(p.name)" :value="p.name">
            {{ p.name }}<template v-if="p.description"> — {{ p.description }}</template>
          </option>
        </select>
        <p
          v-if="profile === 'chatgpt'"
          class="text-amber-600 text-sm mt-1"
          data-testid="chatgpt-warning"
        >
          {{ chatgptWarning }}
        </p>
      </div>
      <div>
        <label class="wf-label">Auth modes</label>
        <div class="flex gap-4 text-sm">
          <label class="flex items-center gap-1">
            <input
              type="checkbox"
              data-testid="auth-mode-oauth"
              :checked="authModes.includes('oauth')"
              @change="toggleAuthMode('oauth', ($event.target as HTMLInputElement).checked)"
            />
            oauth
          </label>
          <label class="flex items-center gap-1">
            <input
              type="checkbox"
              data-testid="auth-mode-api_key"
              :checked="authModes.includes('api_key')"
              @change="toggleAuthMode('api_key', ($event.target as HTMLInputElement).checked)"
            />
            api_key
          </label>
          <label class="flex items-center gap-1">
            <input
              type="checkbox"
              data-testid="auth-mode-none"
              :checked="authModes.includes('none')"
              @change="toggleAuthMode('none', ($event.target as HTMLInputElement).checked)"
            />
            none
          </label>
        </div>
      </div>
      <div>
        <label class="flex items-center gap-1 text-sm">
          <input v-model="enabled" type="checkbox" data-testid="input-enabled" />
          Enabled
        </label>
      </div>
      <div class="grid grid-cols-2 gap-3">
        <div>
          <label class="wf-label">Endpoint rate limit (requests)</label>
          <input
            v-model="rlEndpointLimit"
            type="number"
            class="wf-input"
            data-testid="rl-endpoint-limit"
          />
        </div>
        <div>
          <label class="wf-label">Endpoint window (seconds)</label>
          <input
            v-model="rlEndpointWindow"
            type="number"
            class="wf-input"
            data-testid="rl-endpoint-window"
          />
        </div>
        <div>
          <label class="wf-label">Per-client rate limit (requests)</label>
          <input
            v-model="rlClientLimit"
            type="number"
            class="wf-input"
            data-testid="rl-client-limit"
          />
        </div>
        <div>
          <label class="wf-label">Per-client window (seconds)</label>
          <input
            v-model="rlClientWindow"
            type="number"
            class="wf-input"
            data-testid="rl-client-window"
          />
        </div>
      </div>
      <UButton data-testid="save-endpoint" @click="saveEndpoint">Save</UButton>
    </div>

    <!-- danger zone -->
    <div class="wf-card space-y-3 border-red-300">
      <h2 class="font-medium text-red-600">Danger zone</h2>
      <div>
        <label class="wf-label">Rename endpoint</label>
        <div class="flex items-center gap-2">
          <input v-model="renameInput" class="wf-input" data-testid="rename-input" />
          <label class="flex items-center gap-1 text-sm whitespace-nowrap">
            <input v-model="renameForce" type="checkbox" data-testid="rename-force" />
            force
          </label>
          <UButton variant="outline" data-testid="rename-submit" @click="renameEndpoint">
            Rename
          </UButton>
        </div>
      </div>
      <div>
        <UButton color="error" variant="outline" data-testid="delete-endpoint" @click="deleteEndpoint">
          Delete endpoint
        </UButton>
      </div>
    </div>
  </div>
</template>
