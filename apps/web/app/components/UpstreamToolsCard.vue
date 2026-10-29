<script setup lang="ts">
/** The tools discovery found on an upstream, and asking it again. */
import type { components } from "~~/types/api";

type ToolRead = components["schemas"]["ToolRead"];

const props = defineProps<{ serverName: string; tools: ToolRead[] }>();

const api = useApi();
const refreshResult = ref("");
const staleTools = computed(() => props.tools.filter((t) => t.stale));

const { run, busy, error } = useAction(
  async (prune: boolean) => {
    refreshResult.value = "";
    const result = await api.POST("/api/v1/upstreams/{name}:refresh-tools", {
      params: { path: { name: props.serverName }, query: { prune } },
    });
    const data = result.data;
    if (data) {
      refreshResult.value = data.error
        ? `${CONNECTION_STATE_LABEL[data.connection_state ?? "error"]}: ${data.error}`
        : `${data.discovered} tools, ${data.changed} changed` +
          (prune ? `, ${data.pruned} pruned` : "");
    }
    return result;
  },
  {
    // the probe updates the connection state; bundles and the catalogue show the tools
    invalidates: () => [
      queryKeys.upstreamTools(props.serverName),
      queryKeys.upstream(props.serverName),
      queryKeys.upstreams,
      queryKeys.bundles,
      queryKeys.catalogue,
    ],
  },
);

/** Ask the upstream for its tools again, as connecting does once it can. */
async function refresh() {
  await run(false);
}

async function refreshAndPrune() {
  const names = staleTools.value.map((t) => `  ${t.name}`).join("\n");
  const question =
    `Refresh the tools of "${props.serverName}" and, if the upstream answers, delete these ` +
    `tools it no longer lists, with their curation in every bundle?\n\n${names}`;
  if (!window.confirm(question)) return;
  await run(true);
}

defineExpose({ refresh });
</script>

<template>
  <div class="wf-card space-y-3" data-testid="card-tools">
    <div class="flex items-center gap-3">
      <h2 class="text-sm font-semibold">Tools</h2>
      <UButton size="xs" variant="soft" :loading="busy" data-testid="refresh-tools" @click="refresh"
        >Refresh tools</UButton
      >
      <UButton
        v-if="staleTools.length > 0"
        size="xs"
        color="warning"
        variant="soft"
        :loading="busy"
        data-testid="refresh-and-prune"
        @click="refreshAndPrune"
        >Refresh &amp; prune</UButton
      >
      <span v-if="refreshResult" class="text-sm text-muted" data-testid="refresh-result">{{
        refreshResult
      }}</span>
    </div>
    <p v-if="error" class="text-red-600 text-sm" data-testid="error">{{ error }}</p>
    <div class="overflow-x-auto">
      <table class="wf-table" data-testid="tools-table">
        <thead>
          <tr>
            <th>Name</th>
            <th>Title</th>
            <th>Description</th>
            <th>Last seen</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="t in tools" :key="t.id" :data-testid="`tool-${t.name}`">
            <td>
              {{ t.name }}
              <UBadge
                v-if="t.stale"
                icon="i-lucide-ghost"
                color="warning"
                variant="subtle"
                title="The upstream no longer lists this tool, so no endpoint serves it; its curation is kept in case it returns"
                :data-testid="`tool-stale-${t.name}`"
                >stale</UBadge
              >
            </td>
            <td>{{ t.title }}</td>
            <td>{{ t.description }}</td>
            <td><TimestampText :value="t.last_seen_at" /></td>
          </tr>
          <tr v-if="tools.length === 0">
            <td colspan="4" class="text-muted">No tools discovered.</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
