<script setup lang="ts">
import type { components } from "~~/types/api";

type BundleRead = components["schemas"]["BundleRead"];

const api = useApi();
const errorMsg = ref("");

const { data: bundles, refresh } = await useAsyncData<BundleRead[]>(
  "bundles-list",
  async () => {
    const { data, error } = await api.GET("/api/v1/bundles", {
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
const createDescription = ref("");
const creating = ref(false);

async function createBundle() {
  errorMsg.value = "";
  const name = createName.value.trim();
  // UI-4: client-side validation before submit
  if (!/^[a-zA-Z0-9_-]+$/.test(name)) {
    errorMsg.value = "Name must match ^[a-zA-Z0-9_-]+$";
    return;
  }
  creating.value = true;
  try {
    const { error } = await api.PUT("/api/v1/bundles/{name}", {
      params: { path: { name } },
      body: { name, description: createDescription.value || null },
    });
    if (error) {
      errorMsg.value = apiErrorMessage(error);
      return;
    }
    createName.value = "";
    createDescription.value = "";
    await refresh();
  } finally {
    creating.value = false;
  }
}
</script>

<template>
  <div class="space-y-6">
    <h1 class="text-lg font-semibold">Bundles</h1>

    <p v-if="errorMsg" class="text-red-600 text-sm" data-testid="error">{{ errorMsg }}</p>

    <table class="wf-table" data-testid="bundles-table">
      <thead>
        <tr>
          <th>Name</th>
          <th>Description</th>
          <th>Updated</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="b in bundles" :key="b.name" :data-testid="`row-${b.name}`">
          <td>
            <NuxtLink
              :to="`/bundles/${b.name}`"
              class="inline-flex items-center gap-1.5 underline"
              :data-testid="`open-${b.name}`"
              ><UIcon name="i-lucide-package" class="size-4 text-muted" />{{ b.name }}</NuxtLink
            >
          </td>
          <td>{{ b.description }}</td>
          <td>{{ b.updated_at }}</td>
        </tr>
        <tr v-if="bundles.length === 0">
          <td colspan="3" class="text-muted">No bundles yet.</td>
        </tr>
      </tbody>
    </table>

    <form class="wf-card space-y-3 max-w-xl" @submit.prevent="createBundle">
      <h2 class="text-sm font-semibold">Create bundle</h2>
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
        <label class="wf-label" for="create-description">Description</label>
        <input
          id="create-description"
          v-model="createDescription"
          class="wf-input"
          data-testid="create-description"
        />
      </div>
      <UButton type="submit" size="sm" :loading="creating" data-testid="create-submit"
        >Create</UButton
      >
    </form>
  </div>
</template>
