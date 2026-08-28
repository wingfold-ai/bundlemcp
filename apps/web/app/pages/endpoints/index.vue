<script setup lang="ts">
import type { components } from "~~/types/api";

type EndpointRead = components["schemas"]["EndpointRead"];
type BundleRead = components["schemas"]["BundleRead"];
type EndpointProfile = components["schemas"]["EndpointProfile"];
type EndpointAuthMode = components["schemas"]["EndpointAuthMode"];

interface ProfileInfo {
  name?: string;
  description?: string;
  warning?: string;
  [key: string]: unknown;
}

const api = useApi();

const endpoints = ref<EndpointRead[]>([]);
const bundles = ref<BundleRead[]>([]);
const profiles = ref<ProfileInfo[]>([]);
const errorMsg = ref("");

// UI-4: client-side name validation
const NAME_RE = /^[a-zA-Z0-9_-]+$/;
const RESERVED_NAMES = [
  "api",
  "oauth",
  ".well-known",
  "healthz",
  "readyz",
  "metrics",
  "docs",
  "login",
  "consent",
  "static",
];

function detailMsg(err: unknown): string {
  const d = (err as { detail?: unknown } | null)?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) {
    return d.map((e) => (e as { msg?: string }).msg ?? JSON.stringify(e)).join("; ");
  }
  return "Request failed";
}

async function load() {
  const [eps, bds, profs] = await Promise.all([
    api.GET("/api/v1/endpoints", { params: { query: { offset: 0, limit: 100 } } }),
    api.GET("/api/v1/bundles", { params: { query: { offset: 0, limit: 100 } } }),
    api.GET("/api/v1/endpoints/profiles"),
  ]);
  if (eps.error) {
    errorMsg.value = detailMsg(eps.error);
    return;
  }
  endpoints.value = eps.data?.items ?? [];
  bundles.value = bds.data?.items ?? [];
  profiles.value = (profs.data ?? []) as ProfileInfo[];
}
await load();

// --- create form ---
const createName = ref("");
const createBundle = ref("");
const createProfile = ref<EndpointProfile>("default");
const createAuthModes = ref<EndpointAuthMode[]>(["oauth"]);
const allowUnauthenticated = ref(false);

const selectedProfileInfo = computed(() =>
  profiles.value.find((p) => p.name === createProfile.value),
);
const chatgptWarning = computed(() => {
  if (createProfile.value !== "chatgpt") return "";
  return (
    selectedProfileInfo.value?.warning ??
    "ChatGPT profile re-annotates all tools; verify tool behavior before exposing this endpoint."
  );
});

function toggleAuthMode(mode: EndpointAuthMode, checked: boolean) {
  if (checked) {
    // Client-side rule: "none" only alone.
    if (mode === "none") {
      createAuthModes.value = ["none"];
    } else {
      createAuthModes.value = [
        ...createAuthModes.value.filter((m) => m !== "none" && m !== mode),
        mode,
      ];
    }
  } else {
    createAuthModes.value = createAuthModes.value.filter((m) => m !== mode);
  }
}

function validateCreate(): string {
  if (!NAME_RE.test(createName.value)) {
    return "Name must match ^[a-zA-Z0-9_-]+$";
  }
  if (RESERVED_NAMES.includes(createName.value)) {
    return `Name "${createName.value}" is reserved`;
  }
  if (!createBundle.value) return "Select a bundle";
  if (createAuthModes.value.length === 0) return "Select at least one auth mode";
  if (createAuthModes.value.includes("none") && createAuthModes.value.length > 1) {
    return 'Auth mode "none" cannot be combined with other modes';
  }
  if (createAuthModes.value.includes("none") && !allowUnauthenticated.value) {
    return 'Auth mode "none" requires "allow unauthenticated" to be checked';
  }
  return "";
}

async function createEndpoint() {
  errorMsg.value = validateCreate();
  if (errorMsg.value) return;
  const { error } = await api.PUT("/api/v1/endpoints/{name}", {
    params: { path: { name: createName.value } },
    body: {
      name: createName.value,
      bundle_name: createBundle.value,
      profile: createProfile.value,
      auth_modes: createAuthModes.value,
      allow_unauthenticated: allowUnauthenticated.value,
      enabled: true,
    },
  });
  if (error) {
    errorMsg.value = detailMsg(error);
    return;
  }
  createName.value = "";
  await load();
}
</script>

<template>
  <div class="space-y-6">
    <h1 class="text-lg font-semibold">Endpoints</h1>

    <p v-if="errorMsg" class="text-red-600 text-sm" data-testid="error">{{ errorMsg }}</p>

    <table class="wf-table" data-testid="endpoints-table">
      <thead>
        <tr>
          <th>Name</th>
          <th>Profile</th>
          <th>Auth modes</th>
          <th>Enabled</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="ep in endpoints" :key="ep.id" :data-testid="`row-${ep.name}`">
          <td>
            <NuxtLink
              :to="`/endpoints/${ep.name}`"
              :data-testid="`open-${ep.name}`"
              class="underline"
            >
              {{ ep.name }}
            </NuxtLink>
          </td>
          <td>{{ ep.profile }}</td>
          <td>{{ ep.auth_modes.join(", ") }}</td>
          <td>
            <UBadge :color="ep.enabled ? 'success' : 'neutral'" variant="subtle">
              {{ ep.enabled ? "enabled" : "disabled" }}
            </UBadge>
          </td>
        </tr>
      </tbody>
    </table>

    <div class="wf-card space-y-3">
      <h2 class="font-medium">Create endpoint</h2>
      <div>
        <label class="wf-label">Name</label>
        <input v-model="createName" class="wf-input" data-testid="create-endpoint-name" />
      </div>
      <div>
        <label class="wf-label">Bundle</label>
        <select v-model="createBundle" class="wf-input" data-testid="create-endpoint-bundle">
          <option value="" disabled>Select a bundle</option>
          <option v-for="b in bundles" :key="b.id" :value="b.name">{{ b.name }}</option>
        </select>
      </div>
      <div>
        <label class="wf-label">Profile</label>
        <select v-model="createProfile" class="wf-input" data-testid="create-endpoint-profile">
          <option v-for="p in profiles" :key="String(p.name)" :value="p.name">
            {{ p.name }}<template v-if="p.description"> — {{ p.description }}</template>
          </option>
        </select>
        <p
          v-if="createProfile === 'chatgpt'"
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
              :checked="createAuthModes.includes('oauth')"
              @change="toggleAuthMode('oauth', ($event.target as HTMLInputElement).checked)"
            />
            oauth
          </label>
          <label class="flex items-center gap-1">
            <input
              type="checkbox"
              data-testid="auth-mode-api_key"
              :checked="createAuthModes.includes('api_key')"
              @change="toggleAuthMode('api_key', ($event.target as HTMLInputElement).checked)"
            />
            api_key
          </label>
          <label class="flex items-center gap-1">
            <input
              type="checkbox"
              data-testid="auth-mode-none"
              :checked="createAuthModes.includes('none')"
              @change="toggleAuthMode('none', ($event.target as HTMLInputElement).checked)"
            />
            none
          </label>
        </div>
      </div>
      <div>
        <label class="flex items-center gap-1 text-sm">
          <input
            v-model="allowUnauthenticated"
            type="checkbox"
            data-testid="allow-unauthenticated"
          />
          Allow unauthenticated access (required for auth mode "none")
        </label>
      </div>
      <UButton data-testid="create-endpoint-submit" @click="createEndpoint">Create</UButton>
    </div>
  </div>
</template>
