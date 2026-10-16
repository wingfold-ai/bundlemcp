<script setup lang="ts">
import type { components } from "~~/types/api";

type BundleRead = components["schemas"]["BundleRead"];
type BundleMemberRead = components["schemas"]["BundleMemberRead"];
type BundleToolRead = components["schemas"]["BundleToolRead"];

const api = useApi();
const route = useRoute();
const bundleName = computed(() => String(route.params.name));

const errorMsg = ref("");

// ---- reads ----
const [
  { data: bundle, error: bundleError },
  { data: members, error: membersError },
  { data: tools, error: toolsError },
  { data: profiles },
  { data: allServers, error: serversError },
  { data: endpoints, error: endpointsError },
] = await Promise.all([
  useQuery<BundleRead | null>(
    () => queryKeys.bundle(bundleName.value),
    async () =>
      unwrap(
        await api.GET("/api/v1/bundles/{name}", {
          params: { path: { name: bundleName.value } },
        }),
      ),
    { default: () => null },
  ),
  useQuery<BundleMemberRead[]>(
    () => queryKeys.bundleMembers(bundleName.value),
    async () =>
      unwrap(
        await api.GET("/api/v1/bundles/{name}/upstreams", {
          params: { path: { name: bundleName.value } },
        }),
      ),
    { default: () => [] },
  ),
  useQuery<BundleToolRead[]>(
    () => queryKeys.bundleTools(bundleName.value),
    async () =>
      unwrap(
        await api.GET("/api/v1/bundles/{name}/tools", {
          params: { path: { name: bundleName.value } },
        }),
      ),
    { default: () => [] },
  ),
  useQuery<ProfileInfo[]>(
    queryKeys.profiles,
    async () => unwrap(await api.GET("/api/v1/endpoints/profiles")) as ProfileInfo[],
    { default: () => [] },
  ),
  useUpstreams(),
  useEndpoints(),
]);

// a missing bundle shows "not found" instead of the errors its sub-resources answer with
const notFound = computed(() => bundleError.value?.status === 404);
const loadError = computed(() =>
  notFound.value
    ? ""
    : (bundleError.value ??
        membersError.value ??
        toolsError.value ??
        serversError.value ??
        endpointsError.value)?.message ?? "",
);

// every change to the bundle's members reaches its tools, the grid and the catalogue
async function invalidateMembership() {
  await invalidate(queryKeys.bundle(bundleName.value), queryKeys.composition, queryKeys.catalogue);
}

// ---- meta card ----
const description = ref("");
const overview = ref("");
const saving = ref(false);

watch(
  bundle,
  (b) => {
    description.value = b?.description ?? "";
    overview.value = b?.overview ?? "";
  },
  { immediate: true },
);

async function saveBundle() {
  errorMsg.value = "";
  saving.value = true;
  try {
    const { error } = await api.PUT("/api/v1/bundles/{name}", {
      params: { path: { name: bundleName.value } },
      body: {
        name: bundleName.value,
        description: description.value || null,
        overview: overview.value || null,
      },
    });
    if (error) {
      errorMsg.value = apiErrorMessage(error);
      return;
    }
    await invalidate(queryKeys.bundle(bundleName.value), queryKeys.bundles, queryKeys.catalogue);
  } finally {
    saving.value = false;
  }
}

async function deleteBundle() {
  if (!window.confirm(`Delete bundle "${bundleName.value}"?`)) return;
  errorMsg.value = "";
  const { error } = await api.DELETE("/api/v1/bundles/{name}", {
    params: { path: { name: bundleName.value } },
  });
  if (error) {
    errorMsg.value = apiErrorMessage(error);
    return;
  }
  // the bundle's endpoints go with it
  await navigateTo("/bundles");
  await invalidate(
    queryKeys.bundle(bundleName.value),
    queryKeys.bundles,
    queryKeys.composition,
    queryKeys.endpoints,
    queryKeys.catalogue,
  );
}

// ---- members card ----
const selectedServer = ref("");

const addableServers = computed(() => {
  const memberNames = new Set(members.value.map((m) => m.server_name));
  return allServers.value.filter((s) => !memberNames.has(s.name));
});

async function toggleMember(member: BundleMemberRead, event: Event) {
  errorMsg.value = "";
  const enabled = (event.target as HTMLInputElement).checked;
  const { error } = await api.PUT("/api/v1/bundles/{name}/upstreams/{upstream_name}", {
    params: { path: { name: bundleName.value, upstream_name: member.server_name } },
    body: { enabled },
  });
  if (error) {
    errorMsg.value = apiErrorMessage(error);
  }
  await invalidateMembership();
}

async function removeMember(serverName: string) {
  errorMsg.value = "";
  const { error } = await api.DELETE("/api/v1/bundles/{name}/upstreams/{upstream_name}", {
    params: { path: { name: bundleName.value, upstream_name: serverName } },
  });
  if (error) {
    errorMsg.value = apiErrorMessage(error);
    return;
  }
  await invalidateMembership();
}

async function addMember() {
  errorMsg.value = "";
  if (!selectedServer.value) return;
  const { error } = await api.PUT("/api/v1/bundles/{name}/upstreams/{upstream_name}", {
    params: { path: { name: bundleName.value, upstream_name: selectedServer.value } },
    body: { enabled: true },
  });
  if (error) {
    errorMsg.value = apiErrorMessage(error);
    return;
  }
  selectedServer.value = "";
  await invalidateMembership();
}

// the first member answers first wherever more than one could, such as a resource URI
async function moveMember(index: number, step: -1 | 1) {
  errorMsg.value = "";
  const order = members.value.map((m) => m.server_name);
  const target = index + step;
  if (target < 0 || target >= order.length) return;
  [order[index], order[target]] = [order[target]!, order[index]!];
  const { error } = await api.PUT("/api/v1/bundles/{name}/upstreams:order", {
    params: { path: { name: bundleName.value } },
    body: { upstreams: order },
  });
  if (error) {
    errorMsg.value = apiErrorMessage(error);
    return;
  }
  await invalidateMembership();
}

// ---- tool curation card ----
interface CurationRow {
  enabled: boolean;
  override_name: string;
  override_title: string;
  override_description: string;
  // edited as JSON text, parsed and checked before it is saved
  override_annotations: string;
}
const curation = ref<Record<string, CurationRow>>({});
// what each row was last filled with from the gateway, to tell an edit in progress apart
let seeded: Record<string, CurationRow> = {};

function rowOf(t: BundleToolRead): CurationRow {
  return {
    enabled: t.enabled,
    override_name: t.override_name ?? "",
    override_title: t.override_title ?? "",
    override_description: t.override_description ?? "",
    override_annotations: t.override_annotations ? JSON.stringify(t.override_annotations) : "",
  };
}

const sameRow = (a: CurationRow | undefined, b: CurationRow | undefined) =>
  JSON.stringify(a) === JSON.stringify(b);

// A refetch lands while the admin may be editing another row — after saving one row,
// say — so a row they changed keeps their edit; the rest take the gateway's values.
watch(
  tools,
  (list) => {
    const next: typeof curation.value = {};
    const nextSeeded: typeof seeded = {};
    for (const t of list) {
      const fresh = rowOf(t);
      const current = curation.value[t.tool_id];
      const edited = current !== undefined && !sameRow(current, seeded[t.tool_id]);
      next[t.tool_id] = edited && !sameRow(current, fresh) ? current : fresh;
      // a copy: the form edits its row in place, and the snapshot must not move with it
      nextSeeded[t.tool_id] = { ...fresh };
    }
    curation.value = next;
    seeded = nextSeeded;
  },
  { immediate: true },
);

function isOverridden(t: BundleToolRead): boolean {
  return Boolean(
    t.override_name || t.override_title || t.override_description || t.override_annotations,
  );
}

async function saveCuration(toolId: string) {
  errorMsg.value = "";
  const c = curation.value[toolId];
  if (!c) return;
  let annotations: Record<string, unknown> | null = null;
  if (c.override_annotations.trim()) {
    try {
      annotations = JSON.parse(c.override_annotations);
    } catch {
      annotations = null;
    }
    if (annotations === null || typeof annotations !== "object" || Array.isArray(annotations)) {
      errorMsg.value = 'Override annotations must be a JSON object, e.g. {"readOnlyHint": true}';
      return;
    }
  }
  // the PUT replaces the whole curation record, so every override is sent, not just the
  // ones this row edits
  const { error } = await api.PUT("/api/v1/bundles/{name}/tools/{tool_id}", {
    params: { path: { name: bundleName.value, tool_id: toolId } },
    body: {
      enabled: c.enabled,
      override_name: c.override_name || null,
      override_title: c.override_title || null,
      override_description: c.override_description || null,
      override_annotations: annotations,
    },
  });
  if (error) {
    // 409 (duplicate presented name) surfaces here too
    errorMsg.value = apiErrorMessage(error);
    return;
  }
  await invalidate(queryKeys.bundle(bundleName.value), queryKeys.catalogue);
}

// ---- endpoints card ----
type EndpointProfile = components["schemas"]["EndpointProfile"];
type EndpointAuthMode = components["schemas"]["EndpointAuthMode"];
interface ProfileInfo {
  name?: string;
  description?: string;
  warning?: string;
  [key: string]: unknown;
}

const createName = ref("");
const createProfile = ref<EndpointProfile>("default");
const createAuthModes = ref<EndpointAuthMode[]>(["oauth"]);
const allowUnauthenticated = ref(false);

const profileWarning = computed(
  () => profiles.value.find((p) => p.name === createProfile.value)?.warning ?? "",
);

const endpointNames = computed(() => endpoints.value.map((e) => e.name));
// shown while typing, so a bad, reserved or taken name is seen before anything is sent
const createNameHint = computed(() =>
  createName.value ? nameProblem("endpoint", createName.value, endpointNames.value) : null,
);

function toggleAuthMode(mode: EndpointAuthMode, checked: boolean) {
  if (checked) {
    // Client-side rule: "none" only alone.
    if (mode === "none") {
      createAuthModes.value = ["none"];
    } else {
      createAuthModes.value = [
        ...createAuthModes.value.filter((m) => m !== "none" && m !== mode),
        mode,
      ];
    }
  } else {
    createAuthModes.value = createAuthModes.value.filter((m) => m !== mode);
  }
}

function validateCreate(): string {
  const problem = nameProblem("endpoint", createName.value, endpointNames.value);
  if (problem) return problem;
  if (createAuthModes.value.length === 0) return "Select at least one auth mode";
  if (createAuthModes.value.includes("none") && createAuthModes.value.length > 1) {
    return 'Auth mode "none" cannot be combined with other modes';
  }
  if (createAuthModes.value.includes("none") && !allowUnauthenticated.value) {
    return 'Auth mode "none" requires "allow unauthenticated" to be checked';
  }
  return "";
}

async function createEndpoint() {
  errorMsg.value = validateCreate();
  if (errorMsg.value) return;
  const { error } = await api.PUT("/api/v1/endpoints/{name}", {
    params: { path: { name: createName.value } },
    body: {
      name: createName.value,
      bundle_name: bundleName.value,
      profile: createProfile.value,
      auth_modes: createAuthModes.value,
      allow_unauthenticated: allowUnauthenticated.value,
      enabled: true,
    },
  });
  if (error) {
    errorMsg.value = apiErrorMessage(error);
    return;
  }
  createName.value = "";
  await invalidate(queryKeys.endpoints, queryKeys.bundle(bundleName.value), queryKeys.catalogue);
}

const bundleEndpoints = computed(() =>
  bundle.value ? endpoints.value.filter((e) => e.bundle_id === bundle.value!.id) : [],
);
</script>

<template>
  <div class="space-y-6">
    <h1 class="text-lg font-semibold">Bundle: {{ bundleName }}</h1>

    <p v-if="errorMsg || loadError" class="text-red-600 text-sm" data-testid="error">
      {{ errorMsg || loadError }}
    </p>

    <p v-if="notFound" class="text-muted" data-testid="not-found">not found</p>

    <template v-else-if="bundle">
      <!-- Meta -->
      <div class="wf-card space-y-3 max-w-xl">
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
            One line, sent to the model as this bundle's MCP instructions — keep it short
            (BND-1).
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
        <div class="flex gap-2">
          <UButton size="sm" :loading="saving" data-testid="save-bundle" @click="saveBundle"
            >Save</UButton
          >
          <UButton size="sm" color="error" data-testid="delete-bundle" @click="deleteBundle"
            >Delete bundle</UButton
          >
        </div>
      </div>

      <!-- Members -->
      <div class="wf-card space-y-3">
        <h2 class="text-sm font-semibold">Upstream servers</h2>
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

      <!-- Tool curation -->
      <div class="wf-card space-y-3">
        <h2 class="text-sm font-semibold">Tool curation</h2>
        <div class="overflow-x-auto">
          <table class="wf-table" data-testid="curation-table">
            <thead>
              <tr>
                <th>Upstream</th>
                <th>Upstream name</th>
                <th>Presented name</th>
                <th>Enabled</th>
                <th>Override name</th>
                <th>Override title</th>
                <th>Override description</th>
                <th>Override annotations</th>
                <th />
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="t in tools"
                :key="t.tool_id"
                :data-testid="`curation-${t.server_name}__${t.name}`"
                :data-tool-id="t.tool_id"
              >
                <td>
                  {{ t.server_name }}
                  <UBadge
                    v-if="!t.member_enabled"
                    icon="i-lucide-eye-off"
                    color="neutral"
                    variant="subtle"
                    >member disabled</UBadge
                  >
                  <UBadge
                    v-if="t.stale"
                    icon="i-lucide-ghost"
                    color="warning"
                    variant="subtle"
                    title="The upstream no longer lists this tool, so it is not served; its curation is kept in case it returns"
                    :data-testid="`stale-${t.tool_id}`"
                    >stale</UBadge
                  >
                  <UBadge
                    v-if="t.member_enabled && isOverridden(t)"
                    icon="i-lucide-pencil"
                    color="primary"
                    variant="subtle"
                    title="Presented differently in this bundle than the upstream reports it"
                    :data-testid="`overridden-${t.tool_id}`"
                    >overridden</UBadge
                  >
                </td>
                <td>{{ t.name }}</td>
                <td :data-testid="`presented-${t.tool_id}`">{{ t.presented_name }}</td>
                <td>
                  <input
                    v-if="curation[t.tool_id]"
                    v-model="curation[t.tool_id]!.enabled"
                    type="checkbox"
                    :data-testid="`curation-toggle-${t.tool_id}`"
                  />
                </td>
                <td>
                  <input
                    v-if="curation[t.tool_id]"
                    v-model="curation[t.tool_id]!.override_name"
                    class="wf-input"
                    :data-testid="`override-name-${t.tool_id}`"
                  />
                </td>
                <td>
                  <input
                    v-if="curation[t.tool_id]"
                    v-model="curation[t.tool_id]!.override_title"
                    class="wf-input"
                    :data-testid="`override-title-${t.tool_id}`"
                  />
                </td>
                <td>
                  <textarea
                    v-if="curation[t.tool_id]"
                    v-model="curation[t.tool_id]!.override_description"
                    class="wf-input"
                    rows="2"
                    :placeholder="t.description ?? ''"
                    :data-testid="`override-description-${t.tool_id}`"
                  />
                </td>
                <td>
                  <textarea
                    v-if="curation[t.tool_id]"
                    v-model="curation[t.tool_id]!.override_annotations"
                    class="wf-input font-mono text-xs"
                    rows="2"
                    placeholder='{"readOnlyHint": true}'
                    :data-testid="`override-annotations-${t.tool_id}`"
                  />
                </td>
                <td>
                  <UButton
                    size="xs"
                    variant="soft"
                    :data-testid="`curation-save-${t.tool_id}`"
                    @click="saveCuration(t.tool_id)"
                    >Save</UButton
                  >
                </td>
              </tr>
              <tr v-if="tools.length === 0">
                <td colspan="9" class="text-muted">No tools in this bundle.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- The bundle's own context -->
      <BundlePrompts :bundle-name="bundleName" />
      <BundleResources :bundle-name="bundleName" />

      <!-- Endpoints -->
      <div class="wf-card space-y-4">
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

        <form class="space-y-3 max-w-xl border-t border-muted pt-4" @submit.prevent="createEndpoint">
          <h3 class="text-sm font-medium">Create endpoint</h3>
          <div>
            <label class="wf-label" for="create-endpoint-name">Name (becomes the URL path)</label>
            <input
              id="create-endpoint-name"
              v-model="createName"
              class="wf-input"
              data-testid="create-endpoint-name"
            />
            <p
              v-if="createNameHint"
              class="text-red-600 text-xs mt-1"
              data-testid="create-endpoint-name-hint"
            >
              {{ createNameHint }}
            </p>
          </div>
          <div>
            <label class="wf-label" for="create-endpoint-profile">Profile</label>
            <select
              id="create-endpoint-profile"
              v-model="createProfile"
              class="wf-input"
              data-testid="create-endpoint-profile"
            >
              <option v-for="p in profiles" :key="String(p.name)" :value="p.name">
                {{ p.name }}<template v-if="p.description"> — {{ p.description }}</template>
              </option>
            </select>
            <p
              v-if="profileWarning"
              class="text-amber-600 text-sm mt-1"
              data-testid="profile-warning"
            >
              {{ profileWarning }}
            </p>
          </div>
          <div>
            <span class="wf-label">Auth modes</span>
            <div class="flex gap-4 text-sm">
              <label class="flex items-center gap-1">
                <input
                  type="checkbox"
                  data-testid="auth-mode-oauth"
                  :checked="createAuthModes.includes('oauth')"
                  @change="toggleAuthMode('oauth', ($event.target as HTMLInputElement).checked)"
                />
                oauth
              </label>
              <label class="flex items-center gap-1">
                <input
                  type="checkbox"
                  data-testid="auth-mode-api_key"
                  :checked="createAuthModes.includes('api_key')"
                  @change="toggleAuthMode('api_key', ($event.target as HTMLInputElement).checked)"
                />
                api_key
              </label>
              <label class="flex items-center gap-1">
                <input
                  type="checkbox"
                  data-testid="auth-mode-none"
                  :checked="createAuthModes.includes('none')"
                  @change="toggleAuthMode('none', ($event.target as HTMLInputElement).checked)"
                />
                none
              </label>
            </div>
          </div>
          <label class="flex items-center gap-1 text-sm">
            <input v-model="allowUnauthenticated" type="checkbox" data-testid="allow-unauthenticated" />
            Allow unauthenticated access (required for auth mode "none")
          </label>
          <UButton type="submit" size="sm" data-testid="create-endpoint-submit">Create endpoint</UButton>
        </form>
      </div>
    </template>
  </div>
</template>
