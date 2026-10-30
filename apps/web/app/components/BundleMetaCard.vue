<script setup lang="ts">
/** A bundle's description and catalogue overview, and deleting the bundle. */
import type { components } from "~~/types/api";

type BundleRead = components["schemas"]["BundleRead"];

const props = defineProps<{ bundle: BundleRead }>();

const api = useApi();
// another card's action reads the bundle again; what the admin is typing stays
const description = useEditableField(() => props.bundle.description ?? "");
const overview = useEditableField(() => props.bundle.overview ?? "");

const { run, busy, error } = useCardAction();

async function save() {
  const name = props.bundle.name;
  const saved = await run(() =>
    api.PUT("/api/v1/bundles/{name}", {
      params: { path: { name } },
      body: { name, description: description.value || null, overview: overview.value || null },
    }),
  );
  if (saved) await invalidate(queryKeys.bundle(name), queryKeys.bundles, queryKeys.catalogue);
}

async function remove() {
  const name = props.bundle.name;
  if (!window.confirm(`Delete bundle "${name}"?`)) return;
  const deleted = await run(() =>
    api.DELETE("/api/v1/bundles/{name}", { params: { path: { name } } }),
  );
  if (!deleted) return;
  // the bundle's endpoints go with it
  await navigateTo("/bundles");
  await invalidate(
    queryKeys.bundle(name),
    queryKeys.bundles,
    queryKeys.composition,
    queryKeys.endpoints,
    queryKeys.catalogue,
  );
}
</script>

<template>
  <div class="wf-card space-y-3 max-w-xl" data-testid="card-meta">
    <h2 class="text-sm font-semibold">Meta</h2>
    <div>
      <label class="wf-label" for="input-description">Description</label>
      <input
        id="input-description"
        v-model="description"
        class="wf-input"
        data-testid="input-description"
      />
      <p class="wf-help">
        One line, sent to the model as this bundle's MCP instructions — keep it short (BND-1).
      </p>
    </div>
    <div>
      <label class="wf-label" for="input-overview">Catalogue overview</label>
      <textarea
        id="input-overview"
        v-model="overview"
        rows="6"
        class="wf-input"
        data-testid="input-overview"
      />
      <p class="wf-help">
        Long-form text shown to people on this bundle's catalogue page, above its tools. Never
        sent to a model, so write it for a human: what the bundle is for and anything they must
        set up first. Blank lines start a new paragraph (BND-11).
      </p>
    </div>
    <p v-if="error" class="text-red-600 text-sm" data-testid="error">{{ error }}</p>
    <div class="flex gap-2">
      <UButton size="sm" :loading="busy" data-testid="save-bundle" @click="save">Save</UButton>
      <UButton size="sm" color="error" data-testid="delete-bundle" @click="remove"
        >Delete bundle</UButton
      >
    </div>
  </div>
</template>
