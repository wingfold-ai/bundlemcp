<script setup lang="ts">
const api = useApi();
const errorMsg = ref("");

const { data: bundles, error: loadError } = await useBundles();

const createName = ref("");
const createDescription = ref("");
const creating = ref(false);
// shown while typing, so a bad or taken name is seen before anything is sent
const nameHint = computed(() =>
  createName.value.trim()
    ? nameProblem("bundle", createName.value.trim(), bundles.value.map((b) => b.name))
    : null,
);

async function createBundle() {
  errorMsg.value = "";
  const name = createName.value.trim();
  // client-side validation before submit, against the published rules and the known names
  const problem = nameProblem("bundle", name, bundles.value.map((b) => b.name));
  if (problem) {
    errorMsg.value = problem;
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
    await invalidate(queryKeys.bundles, queryKeys.composition, queryKeys.catalogue);
  } finally {
    creating.value = false;
  }
}
</script>

<template>
  <div class="space-y-6">
    <h1 class="text-lg font-semibold">Bundles</h1>

    <p v-if="errorMsg || loadError" class="text-red-600 text-sm" data-testid="error">
      {{ errorMsg || loadError?.message }}
    </p>

    <div class="overflow-x-auto">
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
            <td><TimestampText :value="b.updated_at" /></td>
          </tr>
          <tr v-if="bundles.length === 0">
            <td colspan="3" class="text-muted">No bundles yet.</td>
          </tr>
        </tbody>
      </table>
    </div>

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
        <p v-if="nameHint" class="text-red-600 text-xs mt-1" data-testid="create-name-hint">
          {{ nameHint }}
        </p>
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
