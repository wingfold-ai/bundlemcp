<script setup lang="ts">
import type { components } from "~~/types/api";

type UpstreamOAuthStatusRead = components["schemas"]["UpstreamOAuthStatusRead"];
type ServerRead = components["schemas"]["ServerRead"];
type ToolRead = components["schemas"]["ToolRead"];

const api = useApi();
const route = useRoute();
const serverName = computed(() => String(route.params.name));

const errorMsg = ref("");
const notFound = ref(false);

// ---- config card state ----
const server = ref<ServerRead | null>(null);
const url = ref("");
const description = ref("");
const authMode = ref<"none" | "static_headers" | "upstream_oauth">("none");
const identityMode = ref<"shared" | "per_user">("shared");
const sendIdentityHeader = ref(true);
const fwdRows = ref<{ key: string; val: string }[]>([]);
const staticHeaderNames = ref<string[]>([]);
const hdrRows = ref<{ key: string; val: string }[]>([]);
const saving = ref(false);

async function loadServer() {
  const { data, error, response } = await api.GET("/api/v1/servers/{name}", {
    params: { path: { name: serverName.value } },
  });
  if (error) {
    if (response?.status === 404) {
      notFound.value = true;
    } else {
      errorMsg.value = apiErrorMessage(error);
    }
    return;
  }
  server.value = data;
  url.value = data.url;
  description.value = data.description ?? "";
  authMode.value = data.auth_mode as typeof authMode.value;
  identityMode.value = data.identity_mode as typeof identityMode.value;
  sendIdentityHeader.value = data.send_identity_header;
  fwdRows.value = Object.entries(data.forward_headers).map(([key, val]) => ({ key, val }));
  staticHeaderNames.value = data.static_header_names ?? [];
  hdrRows.value = [];
}

function addFwdRow() {
  fwdRows.value.push({ key: "", val: "" });
}

function addHdrRow() {
  hdrRows.value.push({ key: "", val: "" });
}

async function saveServer() {
  errorMsg.value = "";
  const forward_headers: Record<string, string> = {};
  for (const r of fwdRows.value) {
    if (r.key.trim()) forward_headers[r.key.trim()] = r.val;
  }
  // empty map keeps existing secrets; only new/replacement pairs are sent
  const static_headers: Record<string, string> = {};
  for (const r of hdrRows.value) {
    if (r.key.trim()) static_headers[r.key.trim()] = r.val;
  }
  saving.value = true;
  try {
    const { error } = await api.PUT("/api/v1/servers/{name}", {
      params: { path: { name: serverName.value } },
      body: {
        name: serverName.value,
        url: url.value.trim(),
        description: description.value || null,
        auth_mode: authMode.value,
        identity_mode: identityMode.value,
        send_identity_header: sendIdentityHeader.value,
        forward_headers,
        static_headers,
      },
    });
    if (error) {
      errorMsg.value = apiErrorMessage(error);
      return;
    }
    await loadServer();
  } finally {
    saving.value = false;
  }
}

// ---- tools card state ----
const tools = ref<ToolRead[]>([]);
const refreshResult = ref("");
const refreshing = ref(false);

async function loadTools() {
  const { data, error } = await api.GET("/api/v1/servers/{name}/tools", {
    params: { path: { name: serverName.value }, query: { offset: 0, limit: 200 } },
  });
  if (error) {
    errorMsg.value = apiErrorMessage(error);
    return;
  }
  tools.value = data.items;
}

async function refreshTools() {
  errorMsg.value = "";
  refreshResult.value = "";
  refreshing.value = true;
  try {
    const { data, error } = await api.POST("/api/v1/servers/{name}:refresh-tools", {
      params: { path: { name: serverName.value } },
    });
    if (error) {
      errorMsg.value = apiErrorMessage(error);
      return;
    }
    const r = data as { discovered?: unknown; changed?: unknown; error?: unknown };
    refreshResult.value = `discovered: ${r.discovered ?? "-"}, changed: ${r.changed ?? "-"}, error: ${r.error ?? "none"}`;
    await loadTools();
  } finally {
    refreshing.value = false;
  }
}

// ---- upstream oauth card state ----
const upstreamStatus = ref<UpstreamOAuthStatusRead | null>(null);
const upClientId = ref("");
const upClientSecret = ref("");
const upAuthUrl = ref("");
const upTokenUrl = ref("");
const upSaving = ref(false);

async function loadUpstreamStatus() {
  const { data, error } = await api.GET("/api/v1/servers/{name}/upstream-oauth", {
    params: { path: { name: serverName.value } },
  });
  if (error) return; // status is optional; missing config is not a page error
  upstreamStatus.value = data;
  upClientId.value = data.client_id ?? "";
  upAuthUrl.value = data.authorization_url ?? "";
  upTokenUrl.value = data.token_url ?? "";
}

async function saveUpstream() {
  errorMsg.value = "";
  upSaving.value = true;
  try {
    const { error } = await api.PUT("/api/v1/servers/{name}/upstream-oauth", {
      params: { path: { name: serverName.value } },
      body: {
        client_id: upClientId.value.trim(),
        client_secret: upClientSecret.value || null,
        authorization_url: upAuthUrl.value.trim() || null,
        token_url: upTokenUrl.value.trim() || null,
      },
    });
    if (error) {
      errorMsg.value = apiErrorMessage(error);
      return;
    }
    upClientSecret.value = "";
    await loadUpstreamStatus();
  } finally {
    upSaving.value = false;
  }
}

async function disconnectUpstream() {
  errorMsg.value = "";
  const { error } = await api.DELETE("/api/v1/servers/{name}/upstream-oauth/token", {
    params: { path: { name: serverName.value } },
  });
  if (error) {
    errorMsg.value = apiErrorMessage(error);
    return;
  }
  await loadUpstreamStatus();
}

const connectUrl = computed(
  () => `${apiBase()}/oauth/upstream/${serverName.value}/connect`,
);

// ---- danger card state ----
const renameName = ref("");
const renameForce = ref(false);

async function renameServer() {
  errorMsg.value = "";
  const newName = renameName.value.trim();
  // UI-4: client-side validation before submit
  if (!/^[a-zA-Z0-9_-]+$/.test(newName)) {
    errorMsg.value = "Name must match ^[a-zA-Z0-9_-]+$";
    return;
  }
  if (newName.includes("__")) {
    errorMsg.value = 'Server name must not contain "__"';
    return;
  }
  const { error } = await api.POST("/api/v1/servers/{name}:rename", {
    params: {
      path: { name: serverName.value },
      query: { new_name: newName, force: renameForce.value },
    },
  });
  if (error) {
    errorMsg.value = apiErrorMessage(error);
    return;
  }
  await navigateTo(`/servers/${newName}`);
}

async function deleteServer() {
  if (!window.confirm(`Delete server "${serverName.value}"?`)) return;
  errorMsg.value = "";
  const { error } = await api.DELETE("/api/v1/servers/{name}", {
    params: { path: { name: serverName.value } },
  });
  if (error) {
    errorMsg.value = apiErrorMessage(error);
    return;
  }
  await navigateTo("/servers");
}

onMounted(async () => {
  await loadServer();
  if (!notFound.value) {
    await Promise.all([loadTools(), loadUpstreamStatus()]);
  }
});
</script>

<template>
  <div class="space-y-6">
    <h1 class="text-lg font-semibold">Server: {{ serverName }}</h1>

    <p v-if="errorMsg" class="text-red-600 text-sm" data-testid="error">{{ errorMsg }}</p>

    <p v-if="notFound" class="text-gray-500" data-testid="not-found">not found</p>

    <template v-else-if="server">
      <!-- Config -->
      <form class="wf-card space-y-3 max-w-2xl" @submit.prevent="saveServer">
        <h2 class="text-sm font-semibold">Configuration</h2>
        <div>
          <label class="wf-label" for="input-url">URL</label>
          <input id="input-url" v-model="url" class="wf-input" data-testid="input-url" />
        </div>
        <div>
          <label class="wf-label" for="input-description">Description</label>
          <input
            id="input-description"
            v-model="description"
            class="wf-input"
            data-testid="input-description"
          />
        </div>
        <div>
          <label class="wf-label" for="input-auth-mode">Auth mode</label>
          <select
            id="input-auth-mode"
            v-model="authMode"
            class="wf-input"
            data-testid="input-auth-mode"
          >
            <option value="none">none</option>
            <option value="static_headers">static_headers</option>
            <option value="upstream_oauth">upstream_oauth</option>
          </select>
        </div>
        <div>
          <label class="wf-label" for="input-identity-mode">Identity mode</label>
          <select
            id="input-identity-mode"
            v-model="identityMode"
            class="wf-input"
            data-testid="input-identity-mode"
          >
            <option value="shared">shared</option>
            <option value="per_user">per_user</option>
          </select>
        </div>
        <div>
          <label class="text-sm">
            <input
              v-model="sendIdentityHeader"
              type="checkbox"
              data-testid="input-send-identity-header"
            />
            Send identity header
          </label>
        </div>

        <div>
          <span class="wf-label">Forward headers (client header &rarr; upstream header)</span>
          <div
            v-for="(row, i) in fwdRows"
            :key="`fwd-${i}`"
            class="flex gap-2 mb-1"
          >
            <input
              v-model="row.key"
              class="wf-input"
              placeholder="client header"
              :data-testid="`fwd-key-${i}`"
            />
            <input
              v-model="row.val"
              class="wf-input"
              placeholder="upstream header"
              :data-testid="`fwd-val-${i}`"
            />
          </div>
          <UButton size="xs" variant="soft" data-testid="fwd-add" @click="addFwdRow"
            >Add forward header</UButton
          >
        </div>

        <div>
          <span class="wf-label">Static headers</span>
          <p class="text-xs text-gray-500 mb-1">
            Existing header values are write-only and never displayed. Leaving this empty keeps
            the existing secrets; add a pair with an existing name to replace its value.
          </p>
          <ul v-if="staticHeaderNames.length" class="text-sm mb-2" data-testid="static-header-names">
            <li v-for="n in staticHeaderNames" :key="n">{{ n }} (value hidden)</li>
          </ul>
          <div
            v-for="(row, i) in hdrRows"
            :key="`hdr-${i}`"
            class="flex gap-2 mb-1"
          >
            <input
              v-model="row.key"
              class="wf-input"
              placeholder="header name"
              :data-testid="`hdr-key-${i}`"
            />
            <input
              v-model="row.val"
              type="password"
              class="wf-input"
              placeholder="value"
              :data-testid="`hdr-val-${i}`"
            />
          </div>
          <UButton size="xs" variant="soft" data-testid="hdr-add" @click="addHdrRow"
            >Add static header</UButton
          >
        </div>

        <UButton type="submit" size="sm" :loading="saving" data-testid="save-server"
          >Save</UButton
        >
      </form>

      <!-- Tools -->
      <div class="wf-card space-y-3">
        <div class="flex items-center gap-3">
          <h2 class="text-sm font-semibold">Tools</h2>
          <UButton
            size="xs"
            variant="soft"
            :loading="refreshing"
            data-testid="refresh-tools"
            @click="refreshTools"
            >Refresh tools</UButton
          >
          <span v-if="refreshResult" class="text-sm text-gray-500" data-testid="refresh-result">{{
            refreshResult
          }}</span>
        </div>
        <table class="wf-table" data-testid="tools-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Title</th>
              <th>Description</th>
              <th>Last seen</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="t in tools" :key="t.id" :data-testid="`tool-${t.name}`">
              <td>{{ t.name }}</td>
              <td>{{ t.title }}</td>
              <td>{{ t.description }}</td>
              <td>{{ t.last_seen_at }}</td>
            </tr>
            <tr v-if="tools.length === 0">
              <td colspan="4" class="text-gray-500">No tools discovered.</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Upstream OAuth -->
      <div class="wf-card space-y-3 max-w-2xl">
        <h2 class="text-sm font-semibold">Upstream OAuth</h2>
        <pre
          class="text-xs bg-gray-50 dark:bg-gray-900 border border-gray-200 rounded p-2 overflow-x-auto"
          data-testid="upstream-status"
          >{{ upstreamStatus ? JSON.stringify(upstreamStatus, null, 2) : "no status" }}</pre
        >
        <form class="space-y-3" @submit.prevent="saveUpstream">
          <div>
            <label class="wf-label" for="upstream-client-id">Client ID</label>
            <input
              id="upstream-client-id"
              v-model="upClientId"
              class="wf-input"
              data-testid="upstream-client-id"
            />
          </div>
          <div>
            <label class="wf-label" for="upstream-client-secret">Client secret</label>
            <input
              id="upstream-client-secret"
              v-model="upClientSecret"
              type="password"
              class="wf-input"
              placeholder="unchanged"
              data-testid="upstream-client-secret"
            />
          </div>
          <div>
            <label class="wf-label" for="upstream-auth-url">Authorization URL</label>
            <input
              id="upstream-auth-url"
              v-model="upAuthUrl"
              class="wf-input"
              data-testid="upstream-auth-url"
            />
          </div>
          <div>
            <label class="wf-label" for="upstream-token-url">Token URL</label>
            <input
              id="upstream-token-url"
              v-model="upTokenUrl"
              class="wf-input"
              data-testid="upstream-token-url"
            />
          </div>
          <div class="flex items-center gap-2">
            <UButton type="submit" size="sm" :loading="upSaving" data-testid="upstream-save"
              >Save OAuth config</UButton
            >
            <a
              :href="connectUrl"
              target="_blank"
              rel="noopener"
              class="text-sm underline"
              data-testid="upstream-connect"
              >Connect</a
            >
            <UButton
              size="sm"
              color="error"
              variant="soft"
              data-testid="upstream-disconnect"
              @click="disconnectUpstream"
              >Disconnect</UButton
            >
          </div>
        </form>
      </div>

      <!-- Danger -->
      <div class="wf-card space-y-3 max-w-2xl">
        <h2 class="text-sm font-semibold">Danger zone</h2>
        <form class="flex items-end gap-2" @submit.prevent="renameServer">
          <div class="grow">
            <label class="wf-label" for="rename-input">New name</label>
            <input
              id="rename-input"
              v-model="renameName"
              class="wf-input"
              data-testid="rename-input"
            />
          </div>
          <label class="text-sm pb-1">
            <input v-model="renameForce" type="checkbox" data-testid="rename-force" />
            force
          </label>
          <UButton type="submit" size="sm" variant="soft" data-testid="rename-submit"
            >Rename</UButton
          >
        </form>
        <UButton size="sm" color="error" data-testid="delete-server" @click="deleteServer"
          >Delete server</UButton
        >
      </div>
    </template>
  </div>
</template>
