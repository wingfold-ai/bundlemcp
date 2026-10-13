<script setup lang="ts">
import type { components } from "~~/types/api";

type AvailableEndpointRead = components["schemas"]["AvailableEndpointRead"];

// The catalogue: the bundles a signed-in person can connect to, grouped
// from the endpoints that accept their identity. Admins see it inside the
// management layout as a preview of what users get.
definePageMeta({ layout: false });

const api = useApi();
const { me } = useMe();
const layout = computed(() => (me.value?.is_admin ? "default" : "user"));

const endpoints = ref<AvailableEndpointRead[]>([]);
const errorMsg = ref("");

async function load() {
  const { data, error } = await api.GET("/api/v1/me/endpoints");
  if (error) {
    errorMsg.value = apiErrorMessage(error);
    return;
  }
  endpoints.value = data ?? [];
}
await load();

interface CatalogueBundle {
  name: string;
  description: string | null;
  endpoints: AvailableEndpointRead[];
}

const bundles = computed<CatalogueBundle[]>(() => {
  const byName = new Map<string, CatalogueBundle>();
  for (const ep of endpoints.value) {
    const entry = byName.get(ep.bundle_name) ?? {
      name: ep.bundle_name,
      description: ep.bundle_description ?? null,
      endpoints: [],
    };
    entry.endpoints.push(ep);
    byName.set(ep.bundle_name, entry);
  }
  return [...byName.values()].sort((a, b) => a.name.localeCompare(b.name));
});
</script>

<template>
  <NuxtLayout :name="layout">
    <div class="space-y-6">
      <div>
        <h1 class="text-lg font-semibold">Bundles you can connect to</h1>
        <p class="text-sm text-muted mt-1">
          Each bundle is a set of tools. Open one to see its endpoints, the URLs you add to your
          MCP client, and sign in there with the same account you used here.
        </p>
      </div>

      <p v-if="errorMsg" class="text-red-600 text-sm" data-testid="error">{{ errorMsg }}</p>

      <div v-if="bundles.length === 0" class="wf-card text-sm text-muted" data-testid="catalogue-empty">
        No bundles are available yet. Ask an administrator to expose one with OAuth.
      </div>

      <div class="grid gap-4 md:grid-cols-2" data-testid="catalogue">
        <NuxtLink
          v-for="b in bundles"
          :key="b.name"
          :to="`/catalogue/${b.name}`"
          class="wf-card block space-y-2 hover:border-primary transition-colors"
          :data-testid="`catalogue-bundle-${b.name}`"
        >
          <h2 class="font-medium inline-flex items-center gap-1.5">
            <UIcon name="i-lucide-package" class="size-4 text-muted" />{{ b.name }}
          </h2>
          <p v-if="b.description" class="text-sm text-toned">{{ b.description }}</p>
          <div class="flex flex-wrap gap-1">
            <UBadge
              v-for="ep in b.endpoints"
              :key="ep.name"
              :icon="PROFILE_ICON[ep.profile]"
              :color="ep.profile === 'default' ? 'neutral' : 'primary'"
              variant="subtle"
              :title="PROFILE_HELP[ep.profile]"
            >
              {{ ep.name }}
            </UBadge>
          </div>
        </NuxtLink>
      </div>
    </div>
  </NuxtLayout>
</template>
