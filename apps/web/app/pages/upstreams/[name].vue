<script setup lang="ts">
import type { components } from "~~/types/api";

type UpstreamOAuthStatusRead = components["schemas"]["UpstreamOAuthStatusRead"];
type ServerRead = components["schemas"]["ServerRead"];
type ToolRead = components["schemas"]["ToolRead"];

const api = useApi();
const route = useRoute();
const serverName = computed(() => String(route.params.name));

const [
  { data: server, error: serverError },
  { data: tools, error: toolsError },
  { data: upstreamStatus },
  { data: upstreams },
] = await Promise.all([
  useQuery<ServerRead | null>(
    () => queryKeys.upstream(serverName.value),
    async () =>
      unwrap(
        await api.GET("/api/v1/upstreams/{name}", {
          params: { path: { name: serverName.value } },
        }),
      ),
    { default: () => null },
  ),
  useQuery<ToolRead[]>(
    () => queryKeys.upstreamTools(serverName.value),
    async () =>
      unwrap(
        await api.GET("/api/v1/upstreams/{name}/tools", {
          params: { path: { name: serverName.value }, query: { offset: 0, limit: 200 } },
        }),
      ).items,
    { default: () => [] },
  ),
  useQuery<UpstreamOAuthStatusRead | null>(
    () => queryKeys.upstreamOAuth(serverName.value),
    async () => {
      const { data, error } = await api.GET("/api/v1/upstreams/{name}/upstream-oauth", {
        params: { path: { name: serverName.value } },
      });
      // status is optional; missing config is not a page error
      return error ? null : data;
    },
    { default: () => null },
  ),
  // read for the rename control, so a taken name is seen before anything is sent
  useUpstreams(),
]);

const notFound = computed(() => serverError.value?.status === 404);
/** A failed read, unless the upstream is missing altogether, which the page says itself. */
const loadErrorMsg = computed(() =>
  notFound.value ? "" : (serverError.value?.message ?? toolsError.value?.message ?? ""),
);

const otherUpstreamNames = computed(() =>
  upstreams.value.map((u) => u.name).filter((n) => n !== serverName.value),
);

const toolsCard = useTemplateRef("toolsCard");

/** What renaming or deleting an upstream changes: every list and bundle that names it. */
const UPSTREAM_DEPENDENTS = [
  queryKeys.upstreams,
  queryKeys.bundles,
  queryKeys.composition,
  queryKeys.catalogue,
];

async function renamed(newName: string) {
  await invalidate(...UPSTREAM_DEPENDENTS);
  await navigateTo(`/upstreams/${newName}`);
}

async function deleted() {
  await invalidate(...UPSTREAM_DEPENDENTS);
  await navigateTo("/upstreams");
}
</script>

<template>
  <div class="space-y-6">
    <h1 class="text-lg font-semibold">Upstream server: {{ serverName }}</h1>

    <p v-if="loadErrorMsg" class="text-red-600 text-sm" data-testid="error">{{ loadErrorMsg }}</p>

    <p v-if="notFound" class="text-muted" data-testid="not-found">not found</p>

    <template v-else-if="server">
      <!-- What the last probe found out -->
      <div class="flex flex-wrap items-center gap-2 text-sm" data-testid="connection-state">
        <UBadge
          :icon="CONNECTION_STATE_ICON[server.connection_state]"
          :color="connectionStateColor(server.connection_state)"
          variant="subtle"
          >{{ CONNECTION_STATE_LABEL[server.connection_state] }}</UBadge
        >
        <span class="text-muted">{{ CONNECTION_STATE_HELP[server.connection_state] }}</span>
        <span v-if="server.protocol_version" class="text-muted">
          · MCP {{ server.protocol_version }}
        </span>
      </div>

      <!-- keyed, so another server always starts from its own values -->
      <UpstreamConfigCard :key="server.id" :server="server" />
      <UpstreamToolsCard ref="toolsCard" :server-name="serverName" :tools="tools" />
      <UpstreamOAuthCard
        v-if="server.auth_mode === 'upstream_oauth'"
        :key="server.id"
        :server-name="serverName"
        :status="upstreamStatus"
        @connected="toolsCard?.refresh()"
      />

      <DangerZoneCard
        kind="upstream"
        :current="serverName"
        :taken="otherUpstreamNames"
        rename-label="New name"
        acknowledgement="Rename it even where a bundle includes it; the tool names clients see change"
        acknowledgement-test-id="rename-force"
        delete-label="Delete upstream"
        delete-test-id="delete-server"
        @renamed="renamed"
        @deleted="deleted"
      />
    </template>
  </div>
</template>
