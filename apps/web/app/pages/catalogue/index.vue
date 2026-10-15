<script setup lang="ts">
import type { components } from "~~/types/api";

type AvailableEndpointRead = components["schemas"]["AvailableEndpointRead"];
type ConsentRead = components["schemas"]["ConsentRead"];

// The catalogue: the bundles a signed-in person can connect to, grouped
// from the endpoints that accept their identity. Admins see it inside the
// management layout as a preview of what users get.
definePageMeta({ layout: false });

const api = useApi();
const { me } = useMe();
const layout = computed(() => (me.value?.is_admin ? "default" : "user"));

const endpoints = ref<AvailableEndpointRead[]>([]);
const errorMsg = ref("");

// the clients this person has authorised; each can be withdrawn here
const consents = ref<ConsentRead[]>([]);

async function load() {
  const { data, error } = await api.GET("/api/v1/me/endpoints");
  if (error) {
    errorMsg.value = apiErrorMessage(error);
    return;
  }
  endpoints.value = data ?? [];
  // a service key has no consents of its own and is answered 401, which shows as none
  const mine = await api.GET("/api/v1/me/consents");
  consents.value = mine.data ?? [];
}
await load();

async function revokeConsent(consentId: string) {
  errorMsg.value = "";
  const { error } = await api.DELETE("/api/v1/me/consents/{consent_id}", {
    params: { path: { consent_id: consentId } },
  });
  if (error) {
    errorMsg.value = apiErrorMessage(error);
    return;
  }
  await load();
}

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

      <div class="space-y-2" data-testid="my-connections">
        <h2 class="font-medium">Your connected clients</h2>
        <p class="text-sm text-muted">
          MCP clients you have allowed to act as you on an endpoint. Withdrawing one signs it out
          there; it asks for your consent again the next time it connects.
        </p>
        <p v-if="consents.length === 0" class="text-sm text-muted" data-testid="my-connections-empty">
          You have not connected any client yet.
        </p>
        <table v-else class="wf-table text-sm">
          <thead>
            <tr>
              <th>Client</th>
              <th>Endpoint</th>
              <th>Connected</th>
              <th />
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in consents" :key="c.id" :data-testid="`my-consent-${c.client_id}`">
              <td class="font-mono text-xs break-all">{{ c.client_id }}</td>
              <td class="font-mono text-xs">{{ c.endpoint_id }}</td>
              <td><TimestampText :value="c.granted_at" /></td>
              <td>
                <UButton
                  size="xs"
                  color="error"
                  variant="outline"
                  :data-testid="`revoke-my-consent-${c.client_id}`"
                  @click="revokeConsent(c.id)"
                >
                  Withdraw
                </UButton>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </NuxtLayout>
</template>
