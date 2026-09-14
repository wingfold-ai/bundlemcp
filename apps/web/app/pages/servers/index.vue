<script setup lang="ts">
import type { components } from "~~/types/api";

type ServerRead = components["schemas"]["ServerRead"];

const api = useApi();
const errorMsg = ref("");


const { data: servers, refresh } = await useAsyncData<ServerRead[]>(
  "servers-list",
  async () => {
    const { data, error } = await api.GET("/api/v1/servers", {
      params: { query: { offset: 0, limit: 100 } },
    });
    if (error) {
      errorMsg.value = apiErrorMessage(error);
      return [];
    }
    return data.items;
  },
  { default: () => [] },
);

const createName = ref("");
const createUrl = ref("");
const createAuthMode = ref<"none" | "static_headers" | "upstream_oauth">("none");
const createIdentityMode = ref<"shared" | "per_user">("shared");
const creating = ref(false);

async function createServer() {
  errorMsg.value = "";
  const name = createName.value.trim();
  // UI-4: client-side validation before submit
  if (!/^[a-zA-Z0-9_-]+$/.test(name)) {
    errorMsg.value = "Name must match ^[a-zA-Z0-9_-]+$";
    return;
  }
  if (name.includes("__")) {
    errorMsg.value = 'Server name must not contain "__"';
    return;
  }
  creating.value = true;
  try {
    const { error } = await api.PUT("/api/v1/servers/{name}", {
      params: { path: { name } },
      body: {
        name,
        url: createUrl.value.trim(),
        auth_mode: createAuthMode.value,
        identity_mode: createIdentityMode.value,
      },
    });
    if (error) {
      errorMsg.value = apiErrorMessage(error);
      return;
    }
    createName.value = "";
    createUrl.value = "";
    createAuthMode.value = "none";
    createIdentityMode.value = "shared";
    await refresh();
  } finally {
    creating.value = false;
  }
}
</script>

<template>
  <div class="space-y-6">
    <h1 class="text-lg font-semibold">Servers</h1>

    <p v-if="errorMsg" class="text-red-600 text-sm" data-testid="error">{{ errorMsg }}</p>

    <table class="wf-table" data-testid="servers-table">
      <thead>
        <tr>
          <th>Name</th>
          <th>URL</th>
          <th>Connection</th>
          <th>Auth</th>
          <th>Health</th>
          <th>Updated</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="s in servers" :key="s.name" :data-testid="`row-${s.name}`">
          <td class="whitespace-nowrap">
            <NuxtLink
              :to="`/servers/${s.name}`"
              class="inline-flex items-center gap-1.5 underline"
              :data-testid="`open-${s.name}`"
              ><UIcon name="i-lucide-server" class="size-4 text-muted" />{{ s.name }}</NuxtLink
            >
          </td>
          <td class="break-all">{{ s.url }}</td>
          <td class="whitespace-nowrap" :data-testid="`connection-${s.name}`">
            <UBadge
              :icon="NETWORK_ICON[connectionKind(s.url).network]"
              :color="connectionKind(s.url).network === 'local' ? 'primary' : 'neutral'"
              variant="subtle"
              :title="
                connectionKind(s.url).network === 'local'
                  ? 'Reached on the gateway\'s own network (compose or cluster), not over the internet'
                  : 'Reached over the internet'
              "
            >
              {{ connectionKind(s.url).network }}
            </UBadge>
            <UBadge color="neutral" variant="outline" class="ml-1">
              {{ connectionKind(s.url).scheme }}
            </UBadge>
          </td>
          <td class="whitespace-nowrap">
            <UBadge
              :icon="AUTH_MODE_ICON[s.auth_mode]"
              :color="s.auth_mode === 'none' ? 'neutral' : 'primary'"
              variant="subtle"
              :title="AUTH_MODE_HELP[s.auth_mode]"
            >
              {{ AUTH_MODE_LABEL[s.auth_mode] }}
            </UBadge>
            <UBadge
              v-if="s.auth_mode === 'upstream_oauth'"
              :icon="IDENTITY_MODE_ICON[s.identity_mode]"
              :color="s.identity_mode === 'per_user' ? 'warning' : 'neutral'"
              variant="subtle"
              class="ml-1"
              :title="IDENTITY_MODE_HELP[s.identity_mode]"
            >
              {{ IDENTITY_MODE_LABEL[s.identity_mode] }}
            </UBadge>
          </td>
          <td>
            <UBadge
              :icon="HEALTH_ICON[s.health_status]"
              :color="healthColor(s.health_status)"
              variant="subtle"
              >{{ s.health_status }}</UBadge
            >
          </td>
          <td class="whitespace-nowrap text-muted">{{ s.updated_at }}</td>
        </tr>
        <tr v-if="servers.length === 0">
          <td colspan="6" class="text-muted">No servers registered.</td>
        </tr>
      </tbody>
    </table>
    <p class="wf-help">
      Every server is reached over Streamable HTTP. <strong>local</strong> means a host on the
      gateway's own network, such as a compose service name; <strong>external</strong> means a
      public host. A stdio-only MCP server runs behind a small HTTP sidecar on the local network
      and is registered by the sidecar's URL.
    </p>

    <form class="wf-card space-y-3 max-w-xl" @submit.prevent="createServer">
      <h2 class="text-sm font-semibold">Register server</h2>
      <div>
        <label class="wf-label" for="create-name">Name</label>
        <input
          id="create-name"
          v-model="createName"
          class="wf-input"
          data-testid="create-name"
        />
      </div>
      <div>
        <label class="wf-label" for="create-url">URL</label>
        <input id="create-url" v-model="createUrl" class="wf-input" data-testid="create-url" />
      </div>
      <div>
        <label class="wf-label" for="create-auth-mode">Auth mode</label>
        <select
          id="create-auth-mode"
          v-model="createAuthMode"
          class="wf-input"
          data-testid="create-auth-mode"
        >
          <option value="none">none — the server needs no credential</option>
          <option value="static_headers">static_headers — API key or token sent as a header</option>
          <option value="upstream_oauth">upstream_oauth — the gateway signs in with OAuth</option>
        </select>
        <p class="wf-help">
          For an API key, choose <em>static_headers</em> and add the header (for example
          <code>authorization: Bearer …</code>) on the server's page after creating it; values are
          stored write-only. For OAuth, configure the client and connect an account on the
          server's page.
        </p>
      </div>
      <div>
        <label class="wf-label" for="create-identity-mode">Identity mode</label>
        <select
          id="create-identity-mode"
          v-model="createIdentityMode"
          class="wf-input"
          data-testid="create-identity-mode"
        >
          <option value="shared">shared — one upstream identity for every caller</option>
          <option value="per_user">per_user — each caller connects their own account</option>
        </select>
        <p class="wf-help">
          Only meaningful with upstream OAuth. <em>shared</em> uses the account an admin connects
          once (a service account). <em>per_user</em> makes each user of an endpoint connect their
          own account the first time they call a tool, so the upstream sees them as themselves.
        </p>
      </div>
      <UButton type="submit" size="sm" :loading="creating" data-testid="create-submit"
        >Create</UButton
      >
    </form>
  </div>
</template>
