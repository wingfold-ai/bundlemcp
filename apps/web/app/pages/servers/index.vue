<script setup lang="ts">
import type { components } from "~~/types/api";

type ServerRead = components["schemas"]["ServerRead"];

const api = useApi();
const errorMsg = ref("");


const { data: servers, refresh } = await useAsyncData<ServerRead[]>(
  "servers-list",
  async () => {
    const { data, error } = await api.GET("/api/v1/servers", {
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

/** A new server opens on its own page, where OAuth connect and tools live. */
async function onCreated(name: string) {
  await refresh();
  await navigateTo(`/servers/${name}`);
}
</script>

<template>
  <div class="space-y-6">
    <h1 class="text-lg font-semibold">Servers</h1>

    <p v-if="errorMsg" class="text-red-600 text-sm" data-testid="error">{{ errorMsg }}</p>

    <table class="wf-table" data-testid="servers-table">
      <thead>
        <tr>
          <th>Name</th>
          <th>URL</th>
          <th>Connection</th>
          <th>Auth</th>
          <th>State</th>
          <th>Health</th>
          <th>Updated</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="s in servers" :key="s.name" :data-testid="`row-${s.name}`">
          <td class="whitespace-nowrap">
            <NuxtLink
              :to="`/servers/${s.name}`"
              class="inline-flex items-center gap-1.5 underline"
              :data-testid="`open-${s.name}`"
              ><UIcon name="i-lucide-server" class="size-4 text-muted" />{{ s.name }}</NuxtLink
            >
          </td>
          <td class="break-all min-w-56">{{ s.url }}</td>
          <td class="whitespace-nowrap" :data-testid="`connection-${s.name}`">
            <UBadge
              :icon="NETWORK_ICON[connectionKind(s.url).network]"
              :color="connectionKind(s.url).network === 'local' ? 'primary' : 'neutral'"
              variant="subtle"
              :title="
                connectionKind(s.url).network === 'local'
                  ? 'Reached on the gateway\'s own network (compose or cluster), not over the internet'
                  : 'Reached over the internet'
              "
            >
              {{ connectionKind(s.url).network }}
            </UBadge>
            <UBadge color="neutral" variant="outline" class="ml-1">
              {{ connectionKind(s.url).scheme }}
            </UBadge>
          </td>
          <td class="whitespace-nowrap">
            <UBadge
              :icon="AUTH_MODE_ICON[s.auth_mode]"
              :color="s.auth_mode === 'none' ? 'neutral' : 'primary'"
              variant="subtle"
              :title="AUTH_MODE_HELP[s.auth_mode]"
            >
              {{ AUTH_MODE_LABEL[s.auth_mode] }}
            </UBadge>
            <UBadge
              v-if="s.auth_mode === 'upstream_oauth'"
              :icon="IDENTITY_MODE_ICON[s.identity_mode]"
              :color="s.identity_mode === 'per_user' ? 'warning' : 'neutral'"
              variant="subtle"
              class="ml-1"
              :title="IDENTITY_MODE_HELP[s.identity_mode]"
            >
              {{ IDENTITY_MODE_LABEL[s.identity_mode] }}
            </UBadge>
          </td>
          <td class="whitespace-nowrap" :data-testid="`state-${s.name}`">
            <UBadge
              :icon="CONNECTION_STATE_ICON[s.connection_state]"
              :color="connectionStateColor(s.connection_state)"
              variant="subtle"
              :title="s.configuration_mismatch || CONNECTION_STATE_HELP[s.connection_state]"
            >
              {{ CONNECTION_STATE_LABEL[s.connection_state] }}
            </UBadge>
          </td>
          <td>
            <UBadge
              :icon="HEALTH_ICON[s.health_status]"
              :color="healthColor(s.health_status)"
              variant="subtle"
              >{{ s.health_status }}</UBadge
            >
          </td>
          <td class="whitespace-nowrap text-muted">{{ s.updated_at }}</td>
        </tr>
        <tr v-if="servers.length === 0">
          <td colspan="7" class="text-muted">No servers registered.</td>
        </tr>
      </tbody>
    </table>
    <p class="wf-help">
      Every server is reached over Streamable HTTP. <strong>local</strong> means a host on the
      gateway's own network, such as a compose service name; <strong>external</strong> means a
      public host. A stdio-only MCP server runs behind a small HTTP sidecar on the local network
      and is registered by the sidecar's URL.
    </p>

    <ServerRegistration @created="onCreated" />
  </div>
</template>
