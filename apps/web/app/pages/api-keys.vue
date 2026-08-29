<script setup lang="ts">
import type { components } from "~~/types/api";

type ApiKeyRead = components["schemas"]["ApiKeyRead"];
type ApiKeyCreated = components["schemas"]["ApiKeyCreated"];

const api = useApi();

const keys = ref<ApiKeyRead[]>([]);
const errorMsg = ref("");
const createdKey = ref<ApiKeyCreated | null>(null);

function detailMsg(err: unknown): string {
  const d = (err as { detail?: unknown } | null)?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) {
    return d.map((e) => (e as { msg?: string }).msg ?? JSON.stringify(e)).join("; ");
  }
  return "Request failed";
}

async function load() {
  const { data, error } = await api.GET("/api/v1/api-keys", {
    params: { query: { offset: 0, limit: 100 } },
  });
  if (error) {
    errorMsg.value = detailMsg(error);
    return;
  }
  keys.value = data?.items ?? [];
}
await load();

// --- create form ---
const keyName = ref("");
const keyKind = ref<"endpoint" | "service">("endpoint");

async function createKey() {
  errorMsg.value = "";
  if (!keyName.value.trim()) {
    errorMsg.value = "Name is required";
    return;
  }
  const { data, error } = await api.POST("/api/v1/api-keys", {
    body: { name: keyName.value, kind: keyKind.value },
  });
  if (error) {
    errorMsg.value = detailMsg(error);
    return;
  }
  createdKey.value = data ?? null;
  keyName.value = "";
  await load();
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
    errorMsg.value = detailMsg(error);
    return;
  }
  await load();
}

async function deleteKey(row: ApiKeyRead) {
  if (!confirm(`Delete API key "${row.name}"?`)) return;
  errorMsg.value = "";
  const { error } = await api.DELETE("/api/v1/api-keys/{key_id}", {
    params: { path: { key_id: row.id } },
  });
  if (error) {
    errorMsg.value = detailMsg(error);
    return;
  }
  await load();
}
</script>

<template>
  <div class="space-y-6">
    <h1 class="text-lg font-semibold">API keys</h1>

    <p v-if="errorMsg" class="text-red-600 text-sm" data-testid="error">{{ errorMsg }}</p>

    <div
      v-if="createdKey"
      class="wf-card border-green-400 space-y-2"
      data-testid="created-key-banner"
    >
      <p class="text-sm font-medium">API key created — shown exactly once. Copy it now.</p>
      <div class="flex items-center gap-2">
        <code
          class="text-sm bg-gray-100 dark:bg-gray-800 rounded px-2 py-1"
          data-testid="created-key-value"
          >{{ createdKey.key }}</code
        >
        <UButton size="sm" variant="outline" data-testid="copy-key" @click="copyCreatedKey">
          Copy
        </UButton>
      </div>
    </div>

    <table class="wf-table" data-testid="keys-table">
      <thead>
        <tr>
          <th>Name</th>
          <th>Prefix</th>
          <th>Kind</th>
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
          <td>
            <UBadge :color="k.is_active ? 'success' : 'neutral'" variant="subtle">
              {{ k.is_active ? "active" : "inactive" }}
            </UBadge>
          </td>
          <td>{{ k.last_used_at ?? "never" }}</td>
          <td class="space-x-2">
            <UButton
              size="xs"
              variant="outline"
              :data-testid="`deactivate-${k.name}`"
              :disabled="!k.is_active"
              @click="deactivateKey(k.id)"
            >
              Deactivate
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

    <div class="wf-card space-y-3">
      <h2 class="font-medium">Create API key</h2>
      <div>
        <label class="wf-label">Name</label>
        <input v-model="keyName" class="wf-input" data-testid="key-name" />
      </div>
      <div>
        <label class="wf-label">Kind</label>
        <select v-model="keyKind" class="wf-input" data-testid="key-kind">
          <option value="endpoint">endpoint</option>
          <option value="service">service</option>
        </select>
      </div>
      <UButton data-testid="key-create" @click="createKey">Create</UButton>
    </div>
  </div>
</template>
