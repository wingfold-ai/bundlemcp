<script setup lang="ts">
/** The upstreams a bundle is made of: enable, order, add and remove them. */
import type { components } from "~~/types/api";

type BundleMemberRead = components["schemas"]["BundleMemberRead"];
type ServerRead = components["schemas"]["ServerRead"];

const props = defineProps<{
  bundleName: string;
  members: BundleMemberRead[];
  /** Every registered upstream, to offer the ones not yet in the bundle. */
  upstreams: ServerRead[];
}>();

const api = useApi();
const selectedServer = ref("");

const addableServers = computed(() => {
  const memberNames = new Set(props.members.map((m) => m.server_name));
  return props.upstreams.filter((s) => !memberNames.has(s.name));
});

// every change to the bundle's members reaches its tools, the grid and the catalogue
const membership = () => [
  queryKeys.bundle(props.bundleName),
  queryKeys.composition,
  queryKeys.catalogue,
];

const { run, error } = useCardAction({ invalidates: membership });

async function toggleMember(member: BundleMemberRead, event: Event) {
  const enabled = (event.target as HTMLInputElement).checked;
  const toggled = await run(() =>
    api.PUT("/api/v1/bundles/{name}/upstreams/{upstream_name}", {
      params: { path: { name: props.bundleName, upstream_name: member.server_name } },
      body: { enabled },
    }),
  );
  // a refused toggle still rereads the members, so the checkbox shows what is stored
  if (!toggled) await invalidate(...membership());
}

async function removeMember(serverName: string) {
  await run(() =>
    api.DELETE("/api/v1/bundles/{name}/upstreams/{upstream_name}", {
      params: { path: { name: props.bundleName, upstream_name: serverName } },
    }),
  );
}

async function addMember() {
  const serverName = selectedServer.value;
  if (!serverName) return;
  const added = await run(() =>
    api.PUT("/api/v1/bundles/{name}/upstreams/{upstream_name}", {
      params: { path: { name: props.bundleName, upstream_name: serverName } },
      body: { enabled: true },
    }),
  );
  if (added) selectedServer.value = "";
}

// the first member answers first wherever more than one could, such as a resource URI
async function moveMember(index: number, step: -1 | 1) {
  const order = props.members.map((m) => m.server_name);
  const target = index + step;
  if (target < 0 || target >= order.length) return;
  [order[index], order[target]] = [order[target]!, order[index]!];
  await run(() =>
    api.PUT("/api/v1/bundles/{name}/upstreams:order", {
      params: { path: { name: props.bundleName } },
      body: { upstreams: order },
    }),
  );
}
</script>

<template>
  <div class="wf-card space-y-3" data-testid="card-members">
    <h2 class="text-sm font-semibold">Upstream servers</h2>
    <p v-if="error" class="text-red-600 text-sm" data-testid="error">{{ error }}</p>
    <div class="overflow-x-auto">
      <table class="wf-table" data-testid="members-table">
        <thead>
          <tr>
            <th>Upstream</th>
            <th>URL</th>
            <th>Health</th>
            <th>Enabled</th>
            <th title="The first member answers first where more than one could">Order</th>
            <th />
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(m, index) in members"
            :key="m.server_name"
            :data-testid="`member-${m.server_name}`"
          >
            <td>
              <NuxtLink
                :to="`/upstreams/${m.server_name}`"
                class="inline-flex items-center gap-1.5 underline"
                ><UIcon name="i-lucide-server" class="size-4 text-muted" />{{
                  m.server_name
                }}</NuxtLink
              >
            </td>
            <td>{{ m.server_url }}</td>
            <td>
              <UBadge
                :icon="HEALTH_ICON[m.health_status]"
                :color="healthColor(m.health_status)"
                variant="subtle"
                >{{ m.health_status }}</UBadge
              >
            </td>
            <td>
              <input
                type="checkbox"
                :checked="m.enabled"
                :data-testid="`member-toggle-${m.server_name}`"
                @change="toggleMember(m, $event)"
              />
            </td>
            <td class="whitespace-nowrap">
              <UButton
                size="xs"
                variant="ghost"
                icon="i-lucide-arrow-up"
                aria-label="Move up"
                :disabled="index === 0"
                :data-testid="`member-up-${m.server_name}`"
                @click="moveMember(index, -1)"
              />
              <UButton
                size="xs"
                variant="ghost"
                icon="i-lucide-arrow-down"
                aria-label="Move down"
                :disabled="index === members.length - 1"
                :data-testid="`member-down-${m.server_name}`"
                @click="moveMember(index, 1)"
              />
            </td>
            <td>
              <UButton
                size="xs"
                color="error"
                variant="soft"
                :data-testid="`member-remove-${m.server_name}`"
                @click="removeMember(m.server_name)"
                >Remove</UButton
              >
            </td>
          </tr>
          <tr v-if="members.length === 0">
            <td colspan="6" class="text-muted">No upstream servers in this bundle.</td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="flex items-center gap-2">
      <select v-model="selectedServer" class="wf-input max-w-xs" data-testid="member-select">
        <option value="" disabled>Select upstream…</option>
        <option v-for="s in addableServers" :key="s.name" :value="s.name">
          {{ s.name }}
        </option>
      </select>
      <UButton size="sm" variant="soft" data-testid="member-add" @click="addMember"
        >Add member</UButton
      >
    </div>
  </div>
</template>
