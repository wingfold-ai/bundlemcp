<script setup lang="ts">
import type { components } from "~~/types/api";

type EndpointRead = components["schemas"]["EndpointRead"];
type EndpointProfile = components["schemas"]["EndpointProfile"];
type EndpointAuthMode = components["schemas"]["EndpointAuthMode"];
type RateLimitConfig = components["schemas"]["RateLimitConfig"];

definePageMeta({ key: (route) => route.fullPath });

const api = useApi();
const route = useRoute();
const name = computed(() => route.params.name as string);

const { data: endpoint, error: loadError } = await useQuery<EndpointRead | null>(
  () => queryKeys.endpoint(name.value),
  async () =>
    unwrap(await api.GET("/api/v1/endpoints/{name}", { params: { path: { name: name.value } } })),
  { default: () => null },
);
const { data: bundles } = await useBundles();
const { data: endpoints } = await useEndpoints();
const { data: profiles } = await useProfiles();

// --- config form state ---
// A refetch of the endpoint keeps what the admin is editing; untouched fields follow it.
const profile = useEditableField<EndpointProfile>(() => endpoint.value?.profile ?? "default");
const authModes = useEditableField<EndpointAuthMode[]>(() => endpoint.value?.auth_modes ?? []);
const enabled = useEditableField(() => endpoint.value?.enabled ?? true);
// one origin per line; "*" alone allows every site
const allowedOrigins = useEditableField(() => (endpoint.value?.allowed_origins ?? []).join("\n"));
// the read model leaves the stored rate limit untyped; it is what was saved as this shape
const storedRateLimit = computed(() => endpoint.value?.rate_limit as RateLimitConfig | null);
// Bound to <input type="number">, for which Vue's v-model assigns a number (or
// "" when the field is cleared) — never assume these hold a string. They are
// filled the same way, so a saved value reads as unchanged once it comes back.
const rlEndpointLimit = useEditableField<string | number>(() =>
  numberField(storedRateLimit.value?.endpoint?.limit),
);
const rlEndpointWindow = useEditableField<string | number>(() =>
  numberField(storedRateLimit.value?.endpoint?.window_seconds),
);
const rlClientLimit = useEditableField<string | number>(() =>
  numberField(storedRateLimit.value?.per_client?.limit),
);
const rlClientWindow = useEditableField<string | number>(() =>
  numberField(storedRateLimit.value?.per_client?.window_seconds),
);

function numberField(value: number | null | undefined): number | "" {
  return value ?? "";
}

/** Every resource whose cached reads show this endpoint. */
function endpointDependents(): string[] {
  return [queryKeys.endpoint(name.value), queryKeys.endpoints, queryKeys.bundles, queryKeys.catalogue];
}

const connectionUrl = computed(() => `${apiBase()}/${name.value}/mcp`);

const bundleName = computed(
  () => bundles.value.find((b) => b.id === endpoint.value?.bundle_id)?.name ?? "",
);

const profileWarning = computed(
  () => profiles.value.find((p) => p.name === profile.value)?.warning ?? "",
);

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

const {
  run: saveEndpoint,
  busy: saving,
  error: configError,
} = useAction(
  async () => {
    if (!bundleName.value) {
      throw new ValidationProblem("Could not resolve bundle name for this endpoint");
    }
    if (authModes.value.length === 0) throw new ValidationProblem("Select at least one auth mode");
    if (authModes.value.includes("none") && authModes.value.length > 1) {
      throw new ValidationProblem('Auth mode "none" cannot be combined with other modes');
    }
    const rateLimit = buildRateLimit();
    return await api.PUT("/api/v1/endpoints/{name}", {
      params: { path: { name: name.value } },
      body: {
        name: name.value,
        bundle_name: bundleName.value,
        profile: profile.value,
        auth_modes: authModes.value,
        allow_unauthenticated: authModes.value.includes("none"),
        enabled: enabled.value,
        allowed_origins: allowedOrigins.value
          .split("\n")
          .map((line) => line.trim())
          .filter((line) => line !== ""),
        ...(rateLimit !== undefined ? { rate_limit: rateLimit } : {}),
      },
    });
  },
  { invalidates: () => endpointDependents() },
);

// --- danger zone ---
// the names a rename would collide with: every endpoint but this one
const otherEndpointNames = computed(() =>
  endpoints.value.map((e) => e.name).filter((n) => n !== name.value),
);

async function renamed(newName: string) {
  await invalidate(...endpointDependents(), queryKeys.endpoint(newName));
  await navigateTo(`/endpoints/${newName}`);
}

async function deleted() {
  // an API key scoped to this endpoint loses it from its scope
  await invalidate(...endpointDependents(), queryKeys.apiKeys);
  await navigateTo("/endpoints");
}
</script>

<template>
  <div class="space-y-6">
    <h1 class="text-lg font-semibold">Endpoint: {{ name }}</h1>

    <p v-if="loadError" class="text-red-600 text-sm" data-testid="error">
      {{ loadError.message }}
    </p>

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
    <div class="wf-card space-y-3" data-testid="card-config">
      <h2 class="font-medium">Configuration</h2>
      <div>
        <label class="wf-label">Profile</label>
        <select v-model="profile" class="wf-input" data-testid="input-profile">
          <option v-for="p in profiles" :key="p.name" :value="p.name">
            {{ p.name }}<template v-if="p.description"> — {{ p.description }}</template>
          </option>
        </select>
        <p
          v-if="profileWarning"
          class="text-amber-600 text-sm mt-1"
          data-testid="profile-warning"
        >
          {{ profileWarning }}
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
      <div>
        <label class="wf-label" for="allowed-origins">Allowed browser origins</label>
        <textarea
          id="allowed-origins"
          v-model="allowedOrigins"
          rows="3"
          class="wf-input font-mono text-sm"
          placeholder="https://app.example"
          data-testid="input-allowed-origins"
        />
        <p class="wf-help">
          Websites whose pages may call this endpoint from a browser, one per line, such as
          <code>https://app.example</code>; <code>*</code> alone allows every site, and an empty list
          allows none but this gateway's own. This is not authentication: scripts and other clients
          that are not browsers are unaffected, and every caller still signs in with the auth modes
          above.
        </p>
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
      <p v-if="configError" class="text-red-600 text-sm" data-testid="error">{{ configError }}</p>
      <UButton :loading="saving" data-testid="save-endpoint" @click="saveEndpoint()">Save</UButton>
    </div>

    <DangerZoneCard
      kind="endpoint"
      class="border-red-300"
      :current="name"
      :taken="otherEndpointNames"
      rename-label="Rename endpoint"
      acknowledgement="I understand that connected clients break"
      require-acknowledgement
      delete-label="Delete endpoint"
      delete-test-id="delete-endpoint"
      @renamed="renamed"
      @deleted="deleted"
    >
      <template #consequence="{ newName }">
        <div class="space-y-2" data-testid="rename-consequence">
          <p>
            The endpoint moves from
            <code data-testid="rename-current-url">{{ connectionUrl }}</code>
            to
            <code data-testid="rename-new-url">{{ `${apiBase()}/${newName}/mcp` }}</code>.
          </p>
          <p class="text-red-600">
            Every MCP client connected to this endpoint stops working until it is reconfigured with the new URL.
          </p>
        </div>
      </template>
    </DangerZoneCard>
  </div>
</template>
