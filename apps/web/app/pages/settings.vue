<script setup lang="ts">
const api = useApi();

const errorMsg = ref("");
const keys = ref<string[]>([]);
const values = ref<Record<string, string>>({});

function asString(v: unknown): string {
  if (typeof v === "string") return v;
  return JSON.stringify(v);
}

function coerce(s: string): unknown {
  if (s === "true") return true;
  if (s === "false") return false;
  if (s.trim() !== "" && !Number.isNaN(Number(s))) return Number(s);
  return s;
}

async function load() {
  const { data, error } = await api.GET("/api/v1/config");
  if (error) {
    errorMsg.value = apiErrorMessage(error);
    return;
  }
  const config = (data ?? {}) as Record<string, unknown>;
  keys.value = Object.keys(config).sort();
  values.value = Object.fromEntries(keys.value.map((k) => [k, asString(config[k])]));
}
await load();

async function saveKey(key: string) {
  errorMsg.value = "";
  const { error } = await api.PUT("/api/v1/config/{key}", {
    params: { path: { key } },
    body: { value: coerce(values.value[key] ?? "") },
  });
  if (error) {
    errorMsg.value = apiErrorMessage(error);
    return;
  }
  await load();
}

async function resetKey(key: string) {
  errorMsg.value = "";
  const { error } = await api.DELETE("/api/v1/config/{key}", {
    params: { path: { key } },
  });
  if (error) {
    errorMsg.value = apiErrorMessage(error);
    return;
  }
  await load();
}
</script>

<template>
  <div class="space-y-6">
    <h1 class="text-lg font-semibold">Settings</h1>

    <p v-if="errorMsg" class="text-red-600 text-sm" data-testid="error">{{ errorMsg }}</p>

    <div class="overflow-x-auto">
      <table class="wf-table wf-table-controls" data-testid="config-table">
        <thead>
          <tr>
            <th>Key</th>
            <th>Value</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="key in keys" :key="key" :data-testid="`config-row-${key}`">
            <td><code>{{ key }}</code></td>
            <td>
              <input v-model="values[key]" class="wf-input" :data-testid="`config-${key}`" />
            </td>
            <td class="space-x-2 whitespace-nowrap">
              <UButton
                size="xs"
                variant="outline"
                :data-testid="`config-save-${key}`"
                @click="saveKey(key)"
              >
                Save
              </UButton>
              <UButton
                size="xs"
                color="neutral"
                variant="outline"
                :data-testid="`config-reset-${key}`"
                @click="resetKey(key)"
              >
                Reset
              </UButton>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
