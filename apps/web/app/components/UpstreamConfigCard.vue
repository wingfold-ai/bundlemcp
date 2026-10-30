<script setup lang="ts">
/**
 * An upstream's stored configuration: URL, credentials, headers and protocol,
 * with the fix a contradicting connection state calls for above it.
 */
import type { components } from "~~/types/api";

type Schemas = components["schemas"];
type ServerRead = Schemas["ServerRead"];

const props = defineProps<{ server: ServerRead }>();

const api = useApi();
// a refetch of the server keeps what the admin is editing; untouched fields follow it
const url = useEditableField(() => props.server.url);
const description = useEditableField(() => props.server.description ?? "");
const authMode = useEditableField<Schemas["ServerAuthMode"]>(() => props.server.auth_mode);
const protocolMode = useEditableField<ServerRead["protocol_mode"]>(
  () => props.server.protocol_mode,
);
const listingSnapshot = useEditableField<Schemas["ListingSnapshotMode"]>(
  () => props.server.listing_snapshot,
);
const identityMode = useEditableField<Schemas["IdentityMode"]>(() => props.server.identity_mode);
const sendIdentityHeader = useEditableField(() => props.server.send_identity_header);
const fwdRows = useEditableField<HeaderRow[]>(() => headersToRows(props.server.forward_headers));
const staticHeaderNames = computed(() => props.server.static_header_names ?? []);
// new or replacement secret values, never filled from the gateway; cleared once saved
const hdrRows = ref<HeaderRow[]>([]);

const forwardsCallerToken = computed(() =>
  fwdRows.value.some((r) => r.key.trim().toLowerCase() === "authorization"),
);

const {
  run: saveConfig,
  busy,
  error,
} = useAction(
  () =>
    api.PUT("/api/v1/upstreams/{name}", {
      params: { path: { name: props.server.name } },
      body: {
        name: props.server.name,
        url: url.value.trim(),
        description: description.value || null,
        auth_mode: authMode.value,
        // whose account only means something for upstream OAuth
        identity_mode: authMode.value === "upstream_oauth" ? identityMode.value : "shared",
        send_identity_header: sendIdentityHeader.value,
        protocol_mode: protocolMode.value,
        listing_snapshot: listingSnapshot.value,
        forward_headers: rowsToHeaders(fwdRows.value, { emptyValue: "keep" }),
        // an empty map keeps the stored secrets; only new or replacement pairs are sent
        static_headers: rowsToHeaders(hdrRows.value, { emptyValue: "keep" }),
      },
    }),
  {
    // the auth and identity mode also change what the OAuth status reports
    invalidates: () => [
      queryKeys.upstream(props.server.name),
      queryKeys.upstreamOAuth(props.server.name),
      queryKeys.upstreams,
    ],
  },
);

async function save() {
  if (await saveConfig()) hdrRows.value = [];
}

/** Apply the change a contradicting connection state calls for. */
async function fixMismatch() {
  if (props.server.connection_state === "oauth_required") {
    authMode.value = "upstream_oauth";
    identityMode.value = "per_user";
    await save();
  } else {
    hdrRows.value = [...hdrRows.value, { key: "", val: "" }];
    document.getElementById("static-headers")?.scrollIntoView({ behavior: "smooth" });
  }
}
</script>

<template>
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

  <form class="wf-card space-y-3 max-w-2xl" data-testid="card-config" @submit.prevent="save()">
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
      <select id="input-auth-mode" v-model="authMode" class="wf-input" data-testid="input-auth-mode">
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
      <HeaderRowsEditor
        v-model="fwdRows"
        key-placeholder="client header"
        value-placeholder="upstream header"
        add-label="Add forward header"
        test-id-prefix="fwd"
      />
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
      <HeaderRowsEditor
        v-model="hdrRows"
        key-placeholder="header name"
        value-placeholder="value"
        value-type="password"
        add-label="Add static header"
        test-id-prefix="hdr"
      />
    </div>

    <details class="text-sm">
      <summary class="cursor-pointer text-muted">Advanced</summary>
      <UpstreamProtocolSettings
        v-model:protocol-mode="protocolMode"
        v-model:listing-snapshot="listingSnapshot"
        id-prefix="input"
        class="mt-2"
      />
    </details>

    <p v-if="error" class="text-red-600 text-sm" data-testid="error">{{ error }}</p>
    <UButton type="submit" size="sm" :loading="busy" data-testid="save-server">Save</UButton>
  </form>
</template>
