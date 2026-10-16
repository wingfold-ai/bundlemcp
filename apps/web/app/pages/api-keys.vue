<script setup lang="ts">
import type { components } from "~~/types/api";

type ApiKeyRead = components["schemas"]["ApiKeyRead"];
type ApiKeyCreated = components["schemas"]["ApiKeyCreated"];

const api = useApi();

const { data: keys, error: loadError } = await useApiKeys();
const { data: endpoints } = await useEndpoints();
const errorMsg = ref("");
const createdKey = ref<ApiKeyCreated | null>(null);

const endpointNameById = computed(() => new Map(endpoints.value.map((e) => [e.id, e.name])));

/** What a key may call: its endpoints by name, every endpoint, or nothing to scope. */
function scopeText(key: ApiKeyRead): string {
  if (key.kind === "service") return "—";
  if (key.endpoint_ids.length === 0) return "every endpoint";
  // a scoped endpoint deleted since keeps its id, the only name it still has
  return key.endpoint_ids.map((id) => endpointNameById.value.get(id) ?? id).join(", ");
}

// --- create form ---
const keyName = ref("");
const keyKind = ref<"endpoint" | "service">("endpoint");
// the endpoints an endpoint key is limited to; none chosen means every endpoint
const keyEndpointIds = ref<string[]>([]);

async function createKey() {
  errorMsg.value = "";
  if (!keyName.value.trim()) {
    errorMsg.value = "Name is required";
    return;
  }
  const { data, error } = await api.POST("/api/v1/api-keys", {
    body: {
      name: keyName.value,
      kind: keyKind.value,
      endpoint_ids: keyKind.value === "endpoint" ? keyEndpointIds.value : [],
    },
  });
  if (error) {
    errorMsg.value = apiErrorMessage(error);
    return;
  }
  createdKey.value = data ?? null;
  keyName.value = "";
  keyEndpointIds.value = [];
  await invalidate(queryKeys.apiKeys);
}

async function copyCreatedKey() {
  if (createdKey.value) await navigator.clipboard.writeText(createdKey.value.key);
}

async function deactivateKey(keyId: string) {
  errorMsg.value = "";
  const { error } = await api.POST("/api/v1/api-keys/{key_id}:deactivate", {
    params: { path: { key_id: keyId } },
  });
  if (error) {
    errorMsg.value = apiErrorMessage(error);
    return;
  }
  await invalidate(queryKeys.apiKeys);
}

// a deactivated key works again under its old secret; nothing about it is reissued
async function activateKey(keyId: string) {
  errorMsg.value = "";
  const { error } = await api.POST("/api/v1/api-keys/{key_id}:activate", {
    params: { path: { key_id: keyId } },
  });
  if (error) {
    errorMsg.value = apiErrorMessage(error);
    return;
  }
  await invalidate(queryKeys.apiKeys);
}

async function deleteKey(row: ApiKeyRead) {
  if (!confirm(`Delete API key "${row.name}"?`)) return;
  errorMsg.value = "";
  const { error } = await api.DELETE("/api/v1/api-keys/{key_id}", {
    params: { path: { key_id: row.id } },
  });
  if (error) {
    errorMsg.value = apiErrorMessage(error);
    return;
  }
  await invalidate(queryKeys.apiKeys);
}
</script>

<template>
  <div class="space-y-6">
    <h1 class="text-lg font-semibold">API keys</h1>

    <p v-if="errorMsg || loadError" class="text-red-600 text-sm" data-testid="error">
      {{ errorMsg || loadError?.message }}
    </p>

    <div
      v-if="createdKey"
      class="wf-card border-green-400 space-y-2"
      data-testid="created-key-banner"
    >
      <p class="text-sm font-medium">API key created — shown exactly once. Copy it now.</p>
      <div class="flex items-center gap-2">
        <code
          class="text-sm bg-elevated rounded px-2 py-1"
          data-testid="created-key-value"
          >{{ createdKey.key }}</code
        >
        <UButton size="sm" variant="outline" data-testid="copy-key" @click="copyCreatedKey">
          Copy
        </UButton>
      </div>
    </div>

    <div class="overflow-x-auto">
      <table class="wf-table" data-testid="keys-table">
        <thead>
          <tr>
            <th>Name</th>
            <th>Prefix</th>
            <th>Kind</th>
            <th>Scope</th>
            <th>Active</th>
            <th>Last used</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="k in keys" :key="k.id" :data-testid="`key-${k.name}`">
            <td>{{ k.name }}</td>
            <td><code>{{ k.key_prefix }}</code></td>
            <td>{{ k.kind }}</td>
            <td :data-testid="`scope-cell-${k.name}`">{{ scopeText(k) }}</td>
            <td>
              <UBadge :color="k.is_active ? 'success' : 'neutral'" variant="subtle">
                {{ k.is_active ? "active" : "inactive" }}
              </UBadge>
            </td>
            <td><TimestampText :value="k.last_used_at" empty="never" /></td>
            <td class="space-x-2">
              <UButton
                v-if="k.is_active"
                size="xs"
                variant="outline"
                :data-testid="`deactivate-${k.name}`"
                @click="deactivateKey(k.id)"
              >
                Deactivate
              </UButton>
              <UButton
                v-else
                size="xs"
                variant="outline"
                :data-testid="`activate-${k.name}`"
                @click="activateKey(k.id)"
              >
                Re-activate
              </UButton>
              <UButton
                size="xs"
                color="error"
                variant="outline"
                :data-testid="`delete-${k.name}`"
                @click="deleteKey(k)"
              >
                Delete
              </UButton>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="wf-card space-y-3">
      <h2 class="font-medium">Create API key</h2>
      <div>
        <label class="wf-label">Name</label>
        <input v-model="keyName" class="wf-input" data-testid="key-name" />
      </div>
      <div>
        <label class="wf-label">Kind</label>
        <select v-model="keyKind" class="wf-input" data-testid="key-kind">
          <option value="endpoint">endpoint — calls MCP endpoints only</option>
          <option value="service">service — also manages the gateway</option>
        </select>
        <p class="wf-help">
          <strong>endpoint</strong> keys are for scripts and agents that use tools: they are accepted
          on endpoints with the <code>api_key</code> auth mode and nowhere else.
          <strong>service</strong> keys can do that too, and additionally call the management API
          (everything this UI does) and the token introspection route, so they are for automation,
          CI, and upstream servers that verify forwarded bearers.
        </p>
      </div>
      <div v-if="keyKind === 'endpoint'" data-testid="key-scope">
        <label class="wf-label">Endpoints</label>
        <div class="flex flex-wrap gap-x-4 gap-y-1 text-sm">
          <label v-for="ep in endpoints" :key="ep.id" class="flex items-center gap-1">
            <input
              v-model="keyEndpointIds"
              type="checkbox"
              :value="ep.id"
              :data-testid="`scope-${ep.name}`"
            />
            {{ ep.name }}
          </label>
        </div>
        <p class="wf-help">
          The endpoints this key is accepted on. Leave every box clear to allow every endpoint,
          including ones created later.
        </p>
      </div>
      <UButton data-testid="key-create" @click="createKey">Create</UButton>
    </div>
  </div>
</template>
