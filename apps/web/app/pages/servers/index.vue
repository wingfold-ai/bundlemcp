<script setup lang="ts">
import type { components } from "~~/types/api";

type ServerRead = components["schemas"]["ServerRead"];

const api = useApi();
const errorMsg = ref("");

function errText(e: unknown): string {
  const d = (e as { detail?: unknown } | null)?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) {
    return d.map((v) => (v as { msg?: string }).msg ?? JSON.stringify(v)).join("; ");
  }
  return "Request failed";
}

const { data: servers, refresh } = await useAsyncData<ServerRead[]>(
  "servers-list",
  async () => {
    const { data, error } = await api.GET("/api/v1/servers", {
      params: { query: { offset: 0, limit: 100 } },
    });
    if (error) {
      errorMsg.value = errText(error);
      return [];
    }
    return data.items;
  },
  { default: () => [] },
);

function healthColor(status: string): "success" | "error" | "neutral" {
  if (status === "ok") return "success";
  if (status === "error") return "error";
  return "neutral";
}

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
      errorMsg.value = errText(error);
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
          <th>Auth mode</th>
          <th>Health</th>
          <th>Updated</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="s in servers" :key="s.name" :data-testid="`row-${s.name}`">
          <td>
            <NuxtLink
              :to="`/servers/${s.name}`"
              class="underline"
              :data-testid="`open-${s.name}`"
              >{{ s.name }}</NuxtLink
            >
          </td>
          <td>{{ s.url }}</td>
          <td>{{ s.auth_mode }}</td>
          <td>
            <UBadge :color="healthColor(s.health_status)" variant="subtle">{{
              s.health_status
            }}</UBadge>
          </td>
          <td>{{ s.updated_at }}</td>
        </tr>
        <tr v-if="servers.length === 0">
          <td colspan="5" class="text-gray-500">No servers registered.</td>
        </tr>
      </tbody>
    </table>

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
          <option value="none">none</option>
          <option value="static_headers">static_headers</option>
          <option value="upstream_oauth">upstream_oauth</option>
        </select>
      </div>
      <div>
        <label class="wf-label" for="create-identity-mode">Identity mode</label>
        <select
          id="create-identity-mode"
          v-model="createIdentityMode"
          class="wf-input"
          data-testid="create-identity-mode"
        >
          <option value="shared">shared</option>
          <option value="per_user">per_user</option>
        </select>
      </div>
      <UButton type="submit" size="sm" :loading="creating" data-testid="create-submit"
        >Create</UButton
      >
    </form>
  </div>
</template>
