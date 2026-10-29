<script setup lang="ts">
/** The public URLs a bundle is served at, and creating another. */
import type { components } from "~~/types/api";

type BundleRead = components["schemas"]["BundleRead"];
type EndpointRead = components["schemas"]["EndpointRead"];
type EndpointProfileRead = components["schemas"]["EndpointProfileRead"];

const props = defineProps<{
  bundle: BundleRead;
  /** Every endpoint, of every bundle: this card shows the bundle's own and checks names against all. */
  endpoints: EndpointRead[];
  profiles: EndpointProfileRead[];
}>();

const bundleEndpoints = computed(() =>
  props.endpoints.filter((e) => e.bundle_id === props.bundle.id),
);
const endpointNames = computed(() => props.endpoints.map((e) => e.name));
</script>

<template>
  <div class="wf-card space-y-4" data-testid="card-endpoints">
    <div>
      <h2 class="text-sm font-semibold">Endpoints</h2>
      <p class="wf-help">
        The public URLs this bundle is served at. Create one per kind of client: OAuth for
        people and their MCP clients, an API key for scripts, and a profile that shapes the
        tools for claude.ai or ChatGPT.
      </p>
    </div>
    <div class="overflow-x-auto">
      <table class="wf-table" data-testid="bundle-endpoints-table">
        <thead>
          <tr>
            <th>Name</th>
            <th>Profile</th>
            <th>Auth modes</th>
            <th>Enabled</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="e in bundleEndpoints" :key="e.name">
            <td class="whitespace-nowrap">
              <NuxtLink
                :to="`/endpoints/${e.name}`"
                class="inline-flex items-center gap-1.5 underline"
                :data-testid="`bundle-endpoint-${e.name}`"
                ><UIcon name="i-lucide-plug-zap" class="size-4 text-muted" />{{ e.name }}</NuxtLink
              >
            </td>
            <td class="whitespace-nowrap">
              <UBadge
                :icon="PROFILE_ICON[e.profile]"
                :color="e.profile === 'default' ? 'neutral' : 'primary'"
                variant="subtle"
                :title="PROFILE_HELP[e.profile]"
                >{{ e.profile }}</UBadge
              >
            </td>
            <td class="whitespace-nowrap space-x-1">
              <UBadge
                v-for="mode in e.auth_modes"
                :key="mode"
                :icon="ENDPOINT_AUTH_ICON[mode]"
                :color="mode === 'none' ? 'warning' : 'neutral'"
                variant="subtle"
                :title="ENDPOINT_AUTH_HELP[mode]"
                >{{ mode }}</UBadge
              >
            </td>
            <td>
              <UBadge
                :icon="e.enabled ? 'i-lucide-circle-check' : 'i-lucide-circle-pause'"
                :color="e.enabled ? 'success' : 'neutral'"
                variant="subtle"
                >{{ e.enabled ? "enabled" : "disabled" }}</UBadge
              >
            </td>
          </tr>
          <tr v-if="bundleEndpoints.length === 0">
            <td colspan="4" class="text-muted">No endpoints yet; this bundle is not reachable.</td>
          </tr>
        </tbody>
      </table>
    </div>

    <EndpointCreateForm :bundle-name="bundle.name" :taken="endpointNames" :profiles="profiles" />
  </div>
</template>
