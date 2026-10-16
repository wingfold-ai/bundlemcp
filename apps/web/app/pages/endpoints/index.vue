<script setup lang="ts">
const { data: endpoints, error: endpointsError } = await useEndpoints();
const { data: bundles } = await useBundles();
const loadError = endpointsError;

const bundleNameById = computed(() => new Map(bundles.value.map((b) => [b.id, b.name])));

</script>

<template>
  <div class="space-y-6">
    <h1 class="text-lg font-semibold">All endpoints</h1>

    <p v-if="loadError" class="text-red-600 text-sm" data-testid="error">
      {{ loadError.message }}
    </p>

    <div class="overflow-x-auto">
      <table class="wf-table" data-testid="endpoints-table">
        <thead>
          <tr>
            <th>Name</th>
            <th>Bundle</th>
            <th>Profile</th>
            <th>Auth modes</th>
            <th>Enabled</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="ep in endpoints" :key="ep.id" :data-testid="`row-${ep.name}`">
            <td>
              <NuxtLink
                :to="`/endpoints/${ep.name}`"
                :data-testid="`open-${ep.name}`"
                class="inline-flex items-center gap-1.5 underline"
              >
                <UIcon name="i-lucide-plug-zap" class="size-4 text-muted" />{{ ep.name }}
              </NuxtLink>
            </td>
            <td :data-testid="`bundle-of-${ep.name}`">
              <NuxtLink
                v-if="bundleNameById.get(ep.bundle_id)"
                :to="`/bundles/${bundleNameById.get(ep.bundle_id)}`"
                class="inline-flex items-center gap-1.5 underline"
              >
                <UIcon name="i-lucide-package" class="size-4 text-muted" />{{ bundleNameById.get(ep.bundle_id) }}
              </NuxtLink>
              <span v-else class="text-muted">—</span>
            </td>
            <td class="whitespace-nowrap">
              <UBadge
                :icon="PROFILE_ICON[ep.profile]"
                :color="ep.profile === 'default' ? 'neutral' : 'primary'"
                variant="subtle"
                :title="PROFILE_HELP[ep.profile]"
              >
                {{ ep.profile }}
              </UBadge>
            </td>
            <td class="whitespace-nowrap space-x-1">
              <UBadge
                v-for="mode in ep.auth_modes"
                :key="mode"
                :icon="ENDPOINT_AUTH_ICON[mode]"
                :color="mode === 'none' ? 'warning' : 'neutral'"
                variant="subtle"
                :title="ENDPOINT_AUTH_HELP[mode]"
              >
                {{ mode }}
              </UBadge>
            </td>
            <td>
              <UBadge
                :icon="ep.enabled ? 'i-lucide-circle-check' : 'i-lucide-circle-pause'"
                :color="ep.enabled ? 'success' : 'neutral'"
                variant="subtle"
              >
                {{ ep.enabled ? "enabled" : "disabled" }}
              </UBadge>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <p class="wf-help">
      Every public URL of this gateway, across all bundles. An endpoint is created on the page of
      the bundle it exposes: open a <NuxtLink to="/bundles" class="underline">bundle</NuxtLink>
      and use its Endpoints card.
    </p>
  </div>
</template>
