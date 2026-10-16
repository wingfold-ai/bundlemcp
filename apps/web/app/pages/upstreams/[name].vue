<script setup lang="ts">
import type { components } from "~~/types/api";

type UpstreamOAuthStatusRead = components["schemas"]["UpstreamOAuthStatusRead"];
type ServerRead = components["schemas"]["ServerRead"];
type ToolRead = components["schemas"]["ToolRead"];

const api = useApi();
const route = useRoute();
const serverName = computed(() => String(route.params.name));

const errorMsg = ref("");

const [
  { data: server, error: serverError },
  { data: tools, error: toolsError },
  { data: upstreamStatus },
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
]);

const notFound = computed(() => serverError.value?.status === 404);
/** A failed read, unless the upstream is missing altogether, which the page says itself. */
const loadErrorMsg = computed(() =>
  notFound.value ? "" : (serverError.value?.message ?? toolsError.value?.message ?? ""),
);

// ---- config card state ----
const url = ref("");
const description = ref("");
const authMode = ref<"none" | "static_headers" | "upstream_oauth" | "delegated_token">("none");
const protocolMode = ref("auto");
const identityMode = ref<"shared" | "per_user">("shared");
const sendIdentityHeader = ref(true);
const fwdRows = ref<{ key: string; val: string }[]>([]);
const staticHeaderNames = ref<string[]>([]);
const hdrRows = ref<{ key: string; val: string }[]>([]);
const saving = ref(false);

function seedServer(data: ServerRead | null) {
  if (!data) return;
  url.value = data.url;
  description.value = data.description ?? "";
  authMode.value = data.auth_mode as typeof authMode.value;
  identityMode.value = data.identity_mode as typeof identityMode.value;
  sendIdentityHeader.value = data.send_identity_header;
  protocolMode.value = data.protocol_mode;
  fwdRows.value = Object.entries(data.forward_headers).map(([key, val]) => ({ key, val }));
  staticHeaderNames.value = data.static_header_names ?? [];
  hdrRows.value = [];
}
watch(server, seedServer, { immediate: true });

function addFwdRow() {
  fwdRows.value.push({ key: "", val: "" });
}

function addHdrRow() {
  hdrRows.value.push({ key: "", val: "" });
}

const forwardsCallerToken = computed(() =>
  fwdRows.value.some((r) => r.key.trim().toLowerCase() === "authorization"),
);

/** Apply the change a contradicting connection state calls for. */
async function fixMismatch() {
  if (server.value?.connection_state === "oauth_required") {
    authMode.value = "upstream_oauth";
    identityMode.value = "per_user";
    await saveServer();
  } else {
    addHdrRow();
    document.getElementById("static-headers")?.scrollIntoView({ behavior: "smooth" });
  }
}

async function saveServer() {
  errorMsg.value = "";
  const forward_headers: Record<string, string> = {};
  for (const r of fwdRows.value) {
    if (r.key.trim()) forward_headers[r.key.trim()] = r.val;
  }
  // empty map keeps existing secrets; only new/replacement pairs are sent
  const static_headers: Record<string, string> = {};
  for (const r of hdrRows.value) {
    if (r.key.trim()) static_headers[r.key.trim()] = r.val;
  }
  saving.value = true;
  try {
    const { error } = await api.PUT("/api/v1/upstreams/{name}", {
      params: { path: { name: serverName.value } },
      body: {
        name: serverName.value,
        url: url.value.trim(),
        description: description.value || null,
        auth_mode: authMode.value,
        // whose account only means something for upstream OAuth
        identity_mode: authMode.value === "upstream_oauth" ? identityMode.value : "shared",
        send_identity_header: sendIdentityHeader.value,
        protocol_mode: protocolMode.value,
        forward_headers,
        static_headers,
      },
    });
    if (error) {
      errorMsg.value = apiErrorMessage(error);
      return;
    }
    // the auth and identity mode also change what the OAuth status reports
    await invalidate(
      queryKeys.upstream(serverName.value),
      queryKeys.upstreamOAuth(serverName.value),
      queryKeys.upstreams,
    );
  } finally {
    saving.value = false;
  }
}

// ---- tools card state ----
const refreshResult = ref("");
const refreshing = ref(false);

const staleTools = computed(() => tools.value.filter((t) => t.stale));

async function refreshAndPrune() {
  const names = staleTools.value.map((t) => `  ${t.name}`).join("\n");
  const question =
    `Refresh the tools of "${serverName.value}" and, if the upstream answers, delete these ` +
    `tools it no longer lists, with their curation in every bundle?\n\n${names}`;
  if (!window.confirm(question)) return;
  await refreshTools(true);
}

async function refreshTools(prune = false) {
  errorMsg.value = "";
  refreshResult.value = "";
  refreshing.value = true;
  try {
    const { data, error } = await api.POST("/api/v1/upstreams/{name}:refresh-tools", {
      params: { path: { name: serverName.value }, query: { prune } },
    });
    if (error) {
      errorMsg.value = apiErrorMessage(error);
      return;
    }
    refreshResult.value = data.error
      ? `${CONNECTION_STATE_LABEL[data.connection_state ?? "error"]}: ${data.error}`
      : `${data.discovered} tools, ${data.changed} changed` +
        (prune ? `, ${data.pruned} pruned` : "");
    // the probe updates the connection state; bundles and the catalogue show the tools
    await invalidate(
      queryKeys.upstreamTools(serverName.value),
      queryKeys.upstream(serverName.value),
      queryKeys.upstreams,
      queryKeys.bundles,
      queryKeys.catalogue,
    );
  } finally {
    refreshing.value = false;
  }
}

// ---- upstream oauth card state ----
const upClientId = ref("");
const upClientSecret = ref("");
const upAuthUrl = ref("");
const upTokenUrl = ref("");
const upGrant = ref<"authorization_code" | "client_credentials">("authorization_code");
const upSaving = ref(false);
const upConnecting = ref(false);

function seedUpstreamStatus(data: UpstreamOAuthStatusRead | null) {
  if (!data) return;
  upClientId.value = data.client_id ?? "";
  upAuthUrl.value = data.authorization_url ?? "";
  upTokenUrl.value = data.token_url ?? "";
  upGrant.value = data.grant_type ?? "authorization_code";
}
watch(upstreamStatus, seedUpstreamStatus, { immediate: true });

async function saveUpstream() {
  errorMsg.value = "";
  upSaving.value = true;
  try {
    const { error } = await api.PUT("/api/v1/upstreams/{name}/upstream-oauth", {
      params: { path: { name: serverName.value } },
      body: {
        client_id: upClientId.value.trim(),
        client_secret: upClientSecret.value || null,
        authorization_url: upAuthUrl.value.trim() || null,
        token_url: upTokenUrl.value.trim() || null,
        grant_type: upGrant.value,
      },
    });
    if (error) {
      errorMsg.value = apiErrorMessage(error);
      return;
    }
    upClientSecret.value = "";
    await invalidate(queryKeys.upstreamOAuth(serverName.value));
  } finally {
    upSaving.value = false;
  }
}

/** a client-credentials client connects with a grant, not a browser sign-in. */
async function connectAsClient() {
  errorMsg.value = "";
  upConnecting.value = true;
  try {
    const { error } = await api.POST("/api/v1/upstreams/{name}/upstream-oauth:connect", {
      params: { path: { name: serverName.value } },
    });
    if (error) {
      errorMsg.value = apiErrorMessage(error);
      return;
    }
    // refreshing the tools invalidates the upstream, its tools and what shows them
    await Promise.all([invalidate(queryKeys.upstreamOAuth(serverName.value)), refreshTools()]);
  } finally {
    upConnecting.value = false;
  }
}

async function disconnectUpstream() {
  errorMsg.value = "";
  const { error } = await api.DELETE("/api/v1/upstreams/{name}/upstream-oauth/token", {
    params: { path: { name: serverName.value } },
  });
  if (error) {
    errorMsg.value = apiErrorMessage(error);
    return;
  }
  // without the token the next probe reports a different connection state
  await invalidate(
    queryKeys.upstreamOAuth(serverName.value),
    queryKeys.upstream(serverName.value),
    queryKeys.upstreams,
  );
}

const connectUrl = computed(
  () => `${apiBase()}/oauth/upstream/${serverName.value}/connect`,
);
const callbackUrl = computed(() => `${apiBase()}/oauth/upstream/callback`);

// ---- danger card state ----
const renameName = ref("");
const renameForce = ref(false);
// shown while typing, so a bad name is seen before anything is sent
const renameHint = computed(() =>
  renameName.value.trim() ? nameProblem("upstream", renameName.value.trim()) : null,
);

/** What renaming or deleting an upstream changes: every list and bundle that names it. */
const UPSTREAM_DEPENDENTS = [
  queryKeys.upstreams,
  queryKeys.bundles,
  queryKeys.composition,
  queryKeys.catalogue,
];

async function renameServer() {
  errorMsg.value = "";
  const newName = renameName.value.trim();
  // client-side validation before submit, against the published rules
  const problem = nameProblem("upstream", newName);
  if (problem) {
    errorMsg.value = problem;
    return;
  }
  const { error } = await api.POST("/api/v1/upstreams/{name}:rename", {
    params: {
      path: { name: serverName.value },
      query: { new_name: newName, force: renameForce.value },
    },
  });
  if (error) {
    errorMsg.value = apiErrorMessage(error);
    return;
  }
  await invalidate(...UPSTREAM_DEPENDENTS);
  renameName.value = "";
  await navigateTo(`/upstreams/${newName}`);
}

async function deleteServer() {
  if (!window.confirm(`Delete upstream "${serverName.value}"?`)) return;
  errorMsg.value = "";
  const { error } = await api.DELETE("/api/v1/upstreams/{name}", {
    params: { path: { name: serverName.value } },
  });
  if (error) {
    errorMsg.value = apiErrorMessage(error);
    return;
  }
  await invalidate(...UPSTREAM_DEPENDENTS);
  await navigateTo("/upstreams");
}
</script>

<template>
  <div class="space-y-6">
    <h1 class="text-lg font-semibold">Upstream server: {{ serverName }}</h1>

    <p v-if="errorMsg || loadErrorMsg" class="text-red-600 text-sm" data-testid="error">
      {{ errorMsg || loadErrorMsg }}
    </p>

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
      <div
        v-if="server.configuration_mismatch"
        class="wf-card border-warning flex flex-wrap items-center gap-3 max-w-2xl"
        data-testid="configuration-mismatch"
      >
        <UIcon name="i-lucide-triangle-alert" class="size-5 text-warning" />
        <span class="text-sm grow">{{ server.configuration_mismatch }}</span>
        <UButton size="xs" data-testid="fix-mismatch" @click="fixMismatch">
          {{ server.connection_state === "oauth_required" ? "Switch to OAuth" : "Add a header" }}
        </UButton>
      </div>

      <!-- Config -->
      <form class="wf-card space-y-3 max-w-2xl" @submit.prevent="saveServer">
        <h2 class="text-sm font-semibold">Configuration</h2>
        <div>
          <label class="wf-label" for="input-url">URL</label>
          <input id="input-url" v-model="url" class="wf-input" data-testid="input-url" />
        </div>
        <div>
          <label class="wf-label" for="input-description">Description</label>
          <input
            id="input-description"
            v-model="description"
            class="wf-input"
            data-testid="input-description"
          />
        </div>
        <div>
          <label class="wf-label" for="input-auth-mode">Auth mode</label>
          <select
            id="input-auth-mode"
            v-model="authMode"
            class="wf-input"
            data-testid="input-auth-mode"
          >
            <option value="none">no credential</option>
            <option value="static_headers">API key / static headers</option>
            <option value="upstream_oauth">upstream OAuth</option>
            <option value="delegated_token">delegated token</option>
          </select>
          <p class="wf-help">
            {{ AUTH_MODE_HELP[authMode] }}.
            <template v-if="authMode === 'none' || authMode === 'static_headers'">
              API keys go in the static headers below; the mode follows from whether any are
              stored.
            </template>
          </p>
        </div>
        <div v-if="authMode === 'upstream_oauth'">
          <label class="wf-label" for="input-identity-mode">Whose account</label>
          <select
            id="input-identity-mode"
            v-model="identityMode"
            class="wf-input"
            data-testid="input-identity-mode"
          >
            <option value="per_user">each user's own account</option>
            <option value="shared">one shared account</option>
          </select>
          <p class="wf-help">{{ IDENTITY_MODE_HELP[identityMode] }}.</p>
        </div>
        <div>
          <label class="text-sm">
            <input
              v-model="sendIdentityHeader"
              type="checkbox"
              data-testid="input-send-identity-header"
            />
            Send the caller's identity as <code>X-MCP-User</code>
          </label>
          <p class="wf-help">
            Useful for your own upstreams on the gateway's network; leave it off for third-party
            upstreams.
          </p>
        </div>

        <div>
          <span class="wf-label">Forward headers (client header &rarr; upstream header)</span>
          <div
            v-for="(row, i) in fwdRows"
            :key="`fwd-${i}`"
            class="flex gap-2 mb-1"
          >
            <input
              v-model="row.key"
              class="wf-input"
              placeholder="client header"
              :data-testid="`fwd-key-${i}`"
            />
            <input
              v-model="row.val"
              class="wf-input"
              placeholder="upstream header"
              :data-testid="`fwd-val-${i}`"
            />
          </div>
          <UButton size="xs" variant="soft" data-testid="fwd-add" @click="addFwdRow"
            >Add forward header</UButton
          >
          <p v-if="forwardsCallerToken" class="wf-help text-warning" data-testid="passthrough-warning">
            Forwarding <code>authorization</code> passes the caller's own gateway token to the
            upstream (token passthrough, which the MCP spec forbids). Prefer the
            <em>delegated token</em> auth mode, which gives the upstream a token bound to it.
          </p>
        </div>

        <div id="static-headers">
          <span class="wf-label">Static headers (API keys, tokens)</span>
          <p class="text-xs text-muted mb-1">
            Sent on every request to this upstream. Values are write-only and never displayed
            again. Leaving this empty keeps the existing secrets; add a pair with an existing
            name to replace its value.
          </p>
          <ul v-if="staticHeaderNames.length" class="text-sm mb-2" data-testid="static-header-names">
            <li v-for="n in staticHeaderNames" :key="n">{{ n }} (value hidden)</li>
          </ul>
          <div
            v-for="(row, i) in hdrRows"
            :key="`hdr-${i}`"
            class="flex gap-2 mb-1"
          >
            <input
              v-model="row.key"
              class="wf-input"
              placeholder="header name"
              :data-testid="`hdr-key-${i}`"
            />
            <input
              v-model="row.val"
              type="password"
              class="wf-input"
              placeholder="value"
              :data-testid="`hdr-val-${i}`"
            />
          </div>
          <UButton size="xs" variant="soft" data-testid="hdr-add" @click="addHdrRow"
            >Add static header</UButton
          >
        </div>

        <details class="text-sm">
          <summary class="cursor-pointer text-muted">Advanced</summary>
          <div class="mt-2">
            <label class="wf-label" for="input-protocol-mode">Protocol</label>
            <select
              id="input-protocol-mode"
              v-model="protocolMode"
              class="wf-input"
              data-testid="input-protocol-mode"
            >
              <option value="auto">auto — negotiate (recommended)</option>
              <option value="legacy">legacy — always the initialize handshake</option>
              <option value="2026-07-28">pin 2026-07-28</option>
            </select>
          </div>
        </details>

        <UButton type="submit" size="sm" :loading="saving" data-testid="save-server"
          >Save</UButton
        >
      </form>

      <!-- Tools -->
      <div class="wf-card space-y-3">
        <div class="flex items-center gap-3">
          <h2 class="text-sm font-semibold">Tools</h2>
          <UButton
            size="xs"
            variant="soft"
            :loading="refreshing"
            data-testid="refresh-tools"
            @click="refreshTools()"
            >Refresh tools</UButton
          >
          <UButton
            v-if="staleTools.length > 0"
            size="xs"
            color="warning"
            variant="soft"
            :loading="refreshing"
            data-testid="refresh-and-prune"
            @click="refreshAndPrune"
            >Refresh &amp; prune</UButton
          >
          <span v-if="refreshResult" class="text-sm text-muted" data-testid="refresh-result">{{
            refreshResult
          }}</span>
        </div>
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

      <!-- Upstream OAuth -->
      <div v-if="server.auth_mode === 'upstream_oauth'" class="wf-card space-y-3 max-w-2xl">
        <h2 class="text-sm font-semibold">Upstream OAuth</h2>
        <p class="wf-help">
          The gateway identifies itself to the upstream's authorization server automatically when
          it can (client metadata document, else dynamic registration), so <em>Connect</em>
          usually works with the fields below left empty. Enter a client only when the provider
          requires one you registered, with the redirect URI <code>{{ callbackUrl }}</code>, or
          for client credentials.
        </p>
        <div class="flex flex-wrap items-center gap-2 text-sm" data-testid="upstream-status">
          <template v-if="!upstreamStatus">
            <UBadge color="neutral" variant="subtle">no status</UBadge>
          </template>
          <template v-else-if="!upstreamStatus.configured">
            <UBadge color="warning" variant="subtle">encryption keys missing</UBadge>
            <span class="text-muted">
              Set BUNDLEMCP_TOKEN_ENCRYPTION_KEYS on the gateway before connecting.
            </span>
          </template>
          <template v-else-if="!upstreamStatus.client_id && !upstreamStatus.shared?.connected">
            <UBadge color="neutral" variant="subtle">no client yet</UBadge>
            <span class="text-muted">obtained automatically on the first connect</span>
          </template>
          <template v-else-if="upstreamStatus.shared?.connected">
            <UBadge :color="upstreamStatus.shared.valid ? 'success' : 'error'" variant="subtle">
              {{ upstreamStatus.shared.valid ? "connected" : "connected, token rejected" }}
            </UBadge>
            <span v-if="upstreamStatus.shared.account_hint" class="text-muted">
              as {{ upstreamStatus.shared.account_hint }}
            </span>
            <span v-if="upstreamStatus.shared.expires_at" class="text-muted">
              · expires <TimestampText :value="upstreamStatus.shared.expires_at" />
            </span>
          </template>
          <template v-else>
            <UBadge color="neutral" variant="subtle">not connected</UBadge>
            <span class="text-muted">
              {{ upstreamStatus.identity_mode === "per_user"
                ? "per-user upstream: each user connects from the link in their first tool call"
                : "click Connect to sign in with the shared account" }}
            </span>
          </template>
        </div>
        <p v-if="upstreamStatus?.identification" class="wf-help mt-0">
          Client: {{ upstreamStatus.identification.replaceAll("_", " ") }}
          <template v-if="upstreamStatus.step_up_scopes?.length">
            · the next connect also requests {{ upstreamStatus.step_up_scopes.join(" ") }}
          </template>
        </p>
        <form class="space-y-3" @submit.prevent="saveUpstream">
          <div>
            <label class="wf-label" for="upstream-grant">Grant</label>
            <select id="upstream-grant" v-model="upGrant" class="wf-input" data-testid="upstream-grant">
              <option value="authorization_code">authorization code — a person signs in</option>
              <option value="client_credentials">
                client credentials — the gateway signs in as this client (shared only)
              </option>
            </select>
          </div>
          <div>
            <label class="wf-label" for="upstream-client-id">Client ID</label>
            <input
              id="upstream-client-id"
              v-model="upClientId"
              class="wf-input"
              data-testid="upstream-client-id"
            />
          </div>
          <div>
            <label class="wf-label" for="upstream-client-secret">Client secret</label>
            <input
              id="upstream-client-secret"
              v-model="upClientSecret"
              type="password"
              class="wf-input"
              placeholder="unchanged"
              data-testid="upstream-client-secret"
            />
          </div>
          <div>
            <label class="wf-label" for="upstream-auth-url">Authorization URL</label>
            <input
              id="upstream-auth-url"
              v-model="upAuthUrl"
              class="wf-input"
              data-testid="upstream-auth-url"
            />
          </div>
          <div>
            <label class="wf-label" for="upstream-token-url">Token URL</label>
            <input
              id="upstream-token-url"
              v-model="upTokenUrl"
              class="wf-input"
              data-testid="upstream-token-url"
            />
          </div>
          <div class="flex items-center gap-2">
            <UButton type="submit" size="sm" :loading="upSaving" data-testid="upstream-save"
              >Save OAuth config</UButton
            >
            <UButton
              v-if="upstreamStatus?.grant_type === 'client_credentials'"
              size="sm"
              variant="soft"
              :loading="upConnecting"
              data-testid="upstream-connect"
              @click="connectAsClient"
              >Connect</UButton
            >
            <a
              v-else
              :href="connectUrl"
              target="_blank"
              rel="noopener"
              class="text-sm underline"
              data-testid="upstream-connect"
              >Connect</a
            >
            <UButton
              size="sm"
              color="error"
              variant="soft"
              data-testid="upstream-disconnect"
              @click="disconnectUpstream"
              >Disconnect</UButton
            >
          </div>
        </form>
      </div>

      <!-- Danger -->
      <div class="wf-card space-y-3 max-w-2xl">
        <h2 class="text-sm font-semibold">Danger zone</h2>
        <form class="flex items-end gap-2" @submit.prevent="renameServer">
          <div class="grow">
            <label class="wf-label" for="rename-input">New name</label>
            <input
              id="rename-input"
              v-model="renameName"
              class="wf-input"
              data-testid="rename-input"
            />
            <p v-if="renameHint" class="text-red-600 text-xs mt-1" data-testid="rename-hint">
              {{ renameHint }}
            </p>
          </div>
          <label class="text-sm pb-1">
            <input v-model="renameForce" type="checkbox" data-testid="rename-force" />
            force
          </label>
          <UButton type="submit" size="sm" variant="soft" data-testid="rename-submit"
            >Rename</UButton
          >
        </form>
        <UButton size="sm" color="error" data-testid="delete-server" @click="deleteServer"
          >Delete upstream</UButton
        >
      </div>
    </template>
  </div>
</template>
