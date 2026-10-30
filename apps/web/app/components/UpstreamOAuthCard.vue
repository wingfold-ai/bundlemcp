<script setup lang="ts">
/** How the gateway signs in to an upstream's authorization server, and its shared connection. */
import type { components } from "~~/types/api";

type Schemas = components["schemas"];
type UpstreamOAuthStatusRead = Schemas["UpstreamOAuthStatusRead"];

const props = defineProps<{ serverName: string; status: UpstreamOAuthStatusRead | null }>();
const emit = defineEmits<{ connected: [] }>();

const api = useApi();
const clientId = ref("");
const clientSecret = ref("");
const authUrl = ref("");
const tokenUrl = ref("");
const grant = ref<Schemas["UpstreamGrant"]>("authorization_code");

watch(
  () => props.status,
  (data) => {
    if (!data) return;
    clientId.value = data.client_id ?? "";
    authUrl.value = data.authorization_url ?? "";
    tokenUrl.value = data.token_url ?? "";
    grant.value = data.grant_type ?? "authorization_code";
  },
  { immediate: true },
);

const connectUrl = computed(() => `${apiBase()}/oauth/upstream/${props.serverName}/connect`);
const callbackUrl = upstreamCallbackUrl();

const { run, busy, error } = useCardAction();

async function save() {
  const saved = await run(() =>
    api.PUT("/api/v1/upstreams/{name}/upstream-oauth", {
      params: { path: { name: props.serverName } },
      body: {
        client_id: clientId.value.trim(),
        client_secret: clientSecret.value || null,
        authorization_url: authUrl.value.trim() || null,
        token_url: tokenUrl.value.trim() || null,
        grant_type: grant.value,
      },
    }),
  );
  if (!saved) return;
  clientSecret.value = "";
  await invalidate(queryKeys.upstreamOAuth(props.serverName));
}

/** A client-credentials client connects with a grant, not a browser sign-in. */
async function connectAsClient() {
  const connected = await run(() =>
    api.POST("/api/v1/upstreams/{name}/upstream-oauth:connect", {
      params: { path: { name: props.serverName } },
    }),
  );
  if (!connected) return;
  emit("connected");
  await invalidate(queryKeys.upstreamOAuth(props.serverName));
}

async function disconnect() {
  const disconnected = await run(() =>
    api.DELETE("/api/v1/upstreams/{name}/upstream-oauth/token", {
      params: { path: { name: props.serverName } },
    }),
  );
  if (!disconnected) return;
  // without the token the next probe reports a different connection state
  await invalidate(
    queryKeys.upstreamOAuth(props.serverName),
    queryKeys.upstream(props.serverName),
    queryKeys.upstreams,
  );
}
</script>

<template>
  <div class="wf-card space-y-3 max-w-2xl" data-testid="card-oauth">
    <h2 class="text-sm font-semibold">Upstream OAuth</h2>
    <p class="wf-help">
      The gateway identifies itself to the upstream's authorization server automatically when
      it can (client metadata document, else dynamic registration), so <em>Connect</em>
      usually works with the fields below left empty. Enter a client only when the provider
      requires one you registered, with the redirect URI <code>{{ callbackUrl }}</code>, or
      for client credentials.
    </p>
    <div class="flex flex-wrap items-center gap-2 text-sm" data-testid="upstream-status">
      <template v-if="!status">
        <UBadge color="neutral" variant="subtle">no status</UBadge>
      </template>
      <template v-else-if="!status.configured">
        <UBadge color="warning" variant="subtle">encryption keys missing</UBadge>
        <span class="text-muted">
          Set BUNDLEMCP_TOKEN_ENCRYPTION_KEYS on the gateway before connecting.
        </span>
      </template>
      <template v-else-if="!status.client_id && !status.shared?.connected">
        <UBadge color="neutral" variant="subtle">no client yet</UBadge>
        <span class="text-muted">obtained automatically on the first connect</span>
      </template>
      <template v-else-if="status.shared?.connected">
        <UBadge :color="status.shared.valid ? 'success' : 'error'" variant="subtle">
          {{ status.shared.valid ? "connected" : "connected, token rejected" }}
        </UBadge>
        <span v-if="status.shared.account_hint" class="text-muted">
          as {{ status.shared.account_hint }}
        </span>
        <span v-if="status.shared.expires_at" class="text-muted">
          · expires <TimestampText :value="status.shared.expires_at" />
        </span>
      </template>
      <template v-else>
        <UBadge color="neutral" variant="subtle">not connected</UBadge>
        <span class="text-muted">
          {{ status.identity_mode === "per_user"
            ? "per-user upstream: each user connects from the link in their first tool call"
            : "click Connect to sign in with the shared account" }}
        </span>
      </template>
    </div>
    <p v-if="status?.identification" class="wf-help mt-0">
      Client: {{ status.identification.replaceAll("_", " ") }}
      <template v-if="status.step_up_scopes?.length">
        · the next connect also requests {{ status.step_up_scopes.join(" ") }}
      </template>
    </p>
    <form class="space-y-3" @submit.prevent="save">
      <div>
        <label class="wf-label" for="upstream-grant">Grant</label>
        <select id="upstream-grant" v-model="grant" class="wf-input" data-testid="upstream-grant">
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
          v-model="clientId"
          class="wf-input"
          data-testid="upstream-client-id"
        />
      </div>
      <div>
        <label class="wf-label" for="upstream-client-secret">Client secret</label>
        <input
          id="upstream-client-secret"
          v-model="clientSecret"
          type="password"
          class="wf-input"
          placeholder="unchanged"
          data-testid="upstream-client-secret"
        />
      </div>
      <div>
        <label class="wf-label" for="upstream-auth-url">Authorization URL</label>
        <input id="upstream-auth-url" v-model="authUrl" class="wf-input" data-testid="upstream-auth-url" />
      </div>
      <div>
        <label class="wf-label" for="upstream-token-url">Token URL</label>
        <input
          id="upstream-token-url"
          v-model="tokenUrl"
          class="wf-input"
          data-testid="upstream-token-url"
        />
      </div>
      <p v-if="error" class="text-red-600 text-sm" data-testid="error">{{ error }}</p>
      <div class="flex items-center gap-2">
        <UButton type="submit" size="sm" :loading="busy" data-testid="upstream-save"
          >Save OAuth config</UButton
        >
        <UButton
          v-if="status?.grant_type === 'client_credentials'"
          size="sm"
          variant="soft"
          :loading="busy"
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
          @click="disconnect"
          >Disconnect</UButton
        >
      </div>
    </form>
  </div>
</template>
