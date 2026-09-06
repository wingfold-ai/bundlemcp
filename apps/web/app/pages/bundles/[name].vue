<script setup lang="ts">
import type { components } from "~~/types/api";

type BundleRead = components["schemas"]["BundleRead"];
type BundleMemberRead = components["schemas"]["BundleMemberRead"];
type BundleToolRead = components["schemas"]["BundleToolRead"];
type ServerRead = components["schemas"]["ServerRead"];
type EndpointRead = components["schemas"]["EndpointRead"];

const api = useApi();
const route = useRoute();
const bundleName = computed(() => String(route.params.name));

const errorMsg = ref("");
const notFound = ref(false);

// ---- meta card ----
const bundle = ref<BundleRead | null>(null);
const description = ref("");
const saving = ref(false);

async function loadBundle() {
  const { data, error, response } = await api.GET("/api/v1/bundles/{name}", {
    params: { path: { name: bundleName.value } },
  });
  if (error) {
    if (response?.status === 404) {
      notFound.value = true;
    } else {
      errorMsg.value = apiErrorMessage(error);
    }
    return;
  }
  bundle.value = data;
  description.value = data.description ?? "";
}

async function saveBundle() {
  errorMsg.value = "";
  saving.value = true;
  try {
    const { error } = await api.PUT("/api/v1/bundles/{name}", {
      params: { path: { name: bundleName.value } },
      body: { name: bundleName.value, description: description.value || null },
    });
    if (error) {
      errorMsg.value = apiErrorMessage(error);
      return;
    }
    await loadBundle();
  } finally {
    saving.value = false;
  }
}

async function deleteBundle() {
  if (!window.confirm(`Delete bundle "${bundleName.value}"?`)) return;
  errorMsg.value = "";
  const { error } = await api.DELETE("/api/v1/bundles/{name}", {
    params: { path: { name: bundleName.value } },
  });
  if (error) {
    errorMsg.value = apiErrorMessage(error);
    return;
  }
  await navigateTo("/bundles");
}

// ---- members card ----
const members = ref<BundleMemberRead[]>([]);
const allServers = ref<ServerRead[]>([]);
const selectedServer = ref("");

async function loadMembers() {
  const { data, error } = await api.GET("/api/v1/bundles/{name}/servers", {
    params: { path: { name: bundleName.value } },
  });
  if (error) {
    errorMsg.value = apiErrorMessage(error);
    return;
  }
  members.value = data;
}

async function loadAllServers() {
  const { data, error } = await api.GET("/api/v1/servers", {
    params: { query: { offset: 0, limit: 100 } },
  });
  if (error) {
    errorMsg.value = apiErrorMessage(error);
    return;
  }
  allServers.value = data.items;
}

const addableServers = computed(() => {
  const memberNames = new Set(members.value.map((m) => m.server_name));
  return allServers.value.filter((s) => !memberNames.has(s.name));
});

async function toggleMember(member: BundleMemberRead, event: Event) {
  errorMsg.value = "";
  const enabled = (event.target as HTMLInputElement).checked;
  const { error } = await api.PUT("/api/v1/bundles/{name}/servers/{server_name}", {
    params: { path: { name: bundleName.value, server_name: member.server_name } },
    body: { enabled },
  });
  if (error) {
    errorMsg.value = apiErrorMessage(error);
  }
  await Promise.all([loadMembers(), loadTools()]);
}

async function removeMember(serverName: string) {
  errorMsg.value = "";
  const { error } = await api.DELETE("/api/v1/bundles/{name}/servers/{server_name}", {
    params: { path: { name: bundleName.value, server_name: serverName } },
  });
  if (error) {
    errorMsg.value = apiErrorMessage(error);
    return;
  }
  await Promise.all([loadMembers(), loadTools()]);
}

async function addMember() {
  errorMsg.value = "";
  if (!selectedServer.value) return;
  const { error } = await api.PUT("/api/v1/bundles/{name}/servers/{server_name}", {
    params: { path: { name: bundleName.value, server_name: selectedServer.value } },
    body: { enabled: true },
  });
  if (error) {
    errorMsg.value = apiErrorMessage(error);
    return;
  }
  selectedServer.value = "";
  await Promise.all([loadMembers(), loadTools()]);
}

// ---- tool curation card ----
const tools = ref<BundleToolRead[]>([]);
const curation = ref<
  Record<string, { enabled: boolean; override_name: string; override_title: string }>
>({});

async function loadTools() {
  const { data, error } = await api.GET("/api/v1/bundles/{name}/tools", {
    params: { path: { name: bundleName.value } },
  });
  if (error) {
    errorMsg.value = apiErrorMessage(error);
    return;
  }
  tools.value = data;
  const next: typeof curation.value = {};
  for (const t of data) {
    next[t.tool_id] = {
      enabled: t.enabled,
      override_name: t.override_name ?? "",
      override_title: t.override_title ?? "",
    };
  }
  curation.value = next;
}

async function saveCuration(toolId: string) {
  errorMsg.value = "";
  const c = curation.value[toolId];
  if (!c) return;
  const { error } = await api.PUT("/api/v1/bundles/{name}/tools/{tool_id}", {
    params: { path: { name: bundleName.value, tool_id: toolId } },
    body: {
      enabled: c.enabled,
      override_name: c.override_name || null,
      override_title: c.override_title || null,
      override_description: null,
    },
  });
  if (error) {
    // 409 (duplicate presented name) surfaces here too
    errorMsg.value = apiErrorMessage(error);
    return;
  }
  await loadTools();
}

// ---- endpoints card ----
const endpoints = ref<EndpointRead[]>([]);

async function loadEndpoints() {
  const { data, error } = await api.GET("/api/v1/endpoints", {
    params: { query: { offset: 0, limit: 200 } },
  });
  if (error) {
    errorMsg.value = apiErrorMessage(error);
    return;
  }
  endpoints.value = data.items;
}

const bundleEndpoints = computed(() =>
  bundle.value ? endpoints.value.filter((e) => e.bundle_id === bundle.value!.id) : [],
);

onMounted(async () => {
  await loadBundle();
  if (!notFound.value) {
    await Promise.all([loadMembers(), loadAllServers(), loadTools(), loadEndpoints()]);
  }
});
</script>

<template>
  <div class="space-y-6">
    <h1 class="text-lg font-semibold">Bundle: {{ bundleName }}</h1>

    <p v-if="errorMsg" class="text-red-600 text-sm" data-testid="error">{{ errorMsg }}</p>

    <p v-if="notFound" class="text-gray-500" data-testid="not-found">not found</p>

    <template v-else-if="bundle">
      <!-- Meta -->
      <div class="wf-card space-y-3 max-w-xl">
        <h2 class="text-sm font-semibold">Meta</h2>
        <div>
          <label class="wf-label" for="input-description">Description</label>
          <input
            id="input-description"
            v-model="description"
            class="wf-input"
            data-testid="input-description"
          />
        </div>
        <div class="flex gap-2">
          <UButton size="sm" :loading="saving" data-testid="save-bundle" @click="saveBundle"
            >Save</UButton
          >
          <UButton size="sm" color="error" data-testid="delete-bundle" @click="deleteBundle"
            >Delete bundle</UButton
          >
        </div>
      </div>

      <!-- Members -->
      <div class="wf-card space-y-3">
        <h2 class="text-sm font-semibold">Member servers</h2>
        <table class="wf-table" data-testid="members-table">
          <thead>
            <tr>
              <th>Server</th>
              <th>URL</th>
              <th>Health</th>
              <th>Enabled</th>
              <th />
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="m in members"
              :key="m.server_name"
              :data-testid="`member-${m.server_name}`"
            >
              <td>
                <NuxtLink :to="`/servers/${m.server_name}`" class="underline">{{
                  m.server_name
                }}</NuxtLink>
              </td>
              <td>{{ m.server_url }}</td>
              <td>
                <UBadge :color="healthColor(m.health_status)" variant="subtle">{{
                  m.health_status
                }}</UBadge>
              </td>
              <td>
                <input
                  type="checkbox"
                  :checked="m.enabled"
                  :data-testid="`member-toggle-${m.server_name}`"
                  @change="toggleMember(m, $event)"
                />
              </td>
              <td>
                <UButton
                  size="xs"
                  color="error"
                  variant="soft"
                  :data-testid="`member-remove-${m.server_name}`"
                  @click="removeMember(m.server_name)"
                  >Remove</UButton
                >
              </td>
            </tr>
            <tr v-if="members.length === 0">
              <td colspan="5" class="text-gray-500">No member servers.</td>
            </tr>
          </tbody>
        </table>
        <div class="flex items-center gap-2">
          <select v-model="selectedServer" class="wf-input max-w-xs" data-testid="member-select">
            <option value="" disabled>Select server…</option>
            <option v-for="s in addableServers" :key="s.name" :value="s.name">
              {{ s.name }}
            </option>
          </select>
          <UButton size="sm" variant="soft" data-testid="member-add" @click="addMember"
            >Add member</UButton
          >
        </div>
      </div>

      <!-- Tool curation -->
      <div class="wf-card space-y-3">
        <h2 class="text-sm font-semibold">Tool curation</h2>
        <table class="wf-table" data-testid="curation-table">
          <thead>
            <tr>
              <th>Server</th>
              <th>Upstream name</th>
              <th>Presented name</th>
              <th>Enabled</th>
              <th>Override name</th>
              <th>Override title</th>
              <th />
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="t in tools"
              :key="t.tool_id"
              :data-testid="`curation-${t.server_name}__${t.name}`"
              :data-tool-id="t.tool_id"
            >
              <td>
                {{ t.server_name }}
                <UBadge v-if="!t.member_enabled" color="neutral" variant="subtle"
                  >member disabled</UBadge
                >
              </td>
              <td>{{ t.name }}</td>
              <td :data-testid="`presented-${t.tool_id}`">{{ t.presented_name }}</td>
              <td>
                <input
                  v-if="curation[t.tool_id]"
                  v-model="curation[t.tool_id]!.enabled"
                  type="checkbox"
                  :data-testid="`curation-toggle-${t.tool_id}`"
                />
              </td>
              <td>
                <input
                  v-if="curation[t.tool_id]"
                  v-model="curation[t.tool_id]!.override_name"
                  class="wf-input"
                  :data-testid="`override-name-${t.tool_id}`"
                />
              </td>
              <td>
                <input
                  v-if="curation[t.tool_id]"
                  v-model="curation[t.tool_id]!.override_title"
                  class="wf-input"
                  :data-testid="`override-title-${t.tool_id}`"
                />
              </td>
              <td>
                <UButton
                  size="xs"
                  variant="soft"
                  :data-testid="`curation-save-${t.tool_id}`"
                  @click="saveCuration(t.tool_id)"
                  >Save</UButton
                >
              </td>
            </tr>
            <tr v-if="tools.length === 0">
              <td colspan="7" class="text-gray-500">No tools in this bundle.</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Endpoints -->
      <div class="wf-card space-y-2">
        <h2 class="text-sm font-semibold">Endpoints serving this bundle</h2>
        <ul class="text-sm">
          <li v-for="e in bundleEndpoints" :key="e.name">
            <NuxtLink
              :to="`/endpoints/${e.name}`"
              class="underline"
              :data-testid="`bundle-endpoint-${e.name}`"
              >{{ e.name }}</NuxtLink
            >
          </li>
          <li v-if="bundleEndpoints.length === 0" class="text-gray-500">No endpoints.</li>
        </ul>
      </div>
    </template>
  </div>
</template>
