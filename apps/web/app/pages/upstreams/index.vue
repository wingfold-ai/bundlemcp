<script setup lang="ts">
const { data: servers, error: loadError } = await useUpstreams();

/** A new upstream opens on its own page, where OAuth connect and tools live. */
async function onCreated(name: string) {
  await invalidate(queryKeys.upstreams, queryKeys.composition);
  await navigateTo(`/upstreams/${name}`);
}
</script>

<template>
  <div class="space-y-6">
    <h1 class="text-lg font-semibold">Upstream servers</h1>

    <p v-if="loadError" class="text-red-600 text-sm" data-testid="error">
      {{ loadError.message }}
    </p>

    <div class="overflow-x-auto">
      <table class="wf-table" data-testid="servers-table">
        <thead>
          <tr>
            <th>Name</th>
            <th>URL</th>
            <th>Connection</th>
            <th>Protocol</th>
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
                :to="`/upstreams/${s.name}`"
                class="inline-flex items-center gap-1.5 underline"
                :data-testid="`open-${s.name}`"
                ><UIcon name="i-lucide-server" class="size-4 text-muted" />{{ s.name }}</NuxtLink
              >
            </td>
            <td class="whitespace-nowrap">
              <span class="block max-w-md truncate" :title="s.url">{{ s.url }}</span>
            </td>
            <td :data-testid="`connection-${s.name}`">
              <div class="flex items-center gap-1">
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
                <UBadge color="neutral" variant="outline">
                  {{ connectionKind(s.url).scheme }}
                </UBadge>
              </div>
            </td>
            <td class="whitespace-nowrap" :data-testid="`protocol-${s.name}`">
              <div class="flex items-center gap-1">
                <UBadge
                  icon="i-lucide-file-badge"
                  :color="protocolLabel(s.protocol_version, s.protocol_mode).known ? 'primary' : 'neutral'"
                  variant="subtle"
                  :title="protocolLabel(s.protocol_version, s.protocol_mode).help"
                >
                  {{ protocolLabel(s.protocol_version, s.protocol_mode).text }}
                </UBadge>
                <UBadge
                  v-if="protocolLabel(s.protocol_version, s.protocol_mode).mode"
                  color="neutral"
                  variant="outline"
                  title="The negotiation rule configured for this upstream, rather than the default probe-then-handshake"
                >
                  {{ protocolLabel(s.protocol_version, s.protocol_mode).mode }}
                </UBadge>
              </div>
            </td>
            <td>
              <div class="flex items-center gap-1">
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
                  :title="IDENTITY_MODE_HELP[s.identity_mode]"
                >
                  {{ IDENTITY_MODE_LABEL[s.identity_mode] }}
                </UBadge>
              </div>
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
            <td class="text-muted"><TimestampText :value="s.updated_at" /></td>
          </tr>
          <tr v-if="servers.length === 0">
            <td colspan="8" class="text-muted">No upstream servers registered.</td>
          </tr>
        </tbody>
      </table>
    </div>
    <p class="wf-help">
      <strong>Protocol</strong> is the MCP revision the gateway negotiated with the upstream at its
      last successful probe; a dash means it has not been reached yet. Every upstream is reached over
      Streamable HTTP. <strong>local</strong> means a host on the
      gateway's own network, such as a compose service name; <strong>external</strong> means a
      public host. A stdio-only MCP server runs behind a small HTTP sidecar on the local network
      and is registered by the sidecar's URL.
    </p>

    <ServerRegistration @created="onCreated" />
  </div>
</template>
