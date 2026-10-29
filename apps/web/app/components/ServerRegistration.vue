<script setup lang="ts">
/**
 * Guided server registration: start from the URL, let the gateway inspect
 * it, and ask only what the upstream cannot answer — where the credential
 * comes from — with the detected answer pre-selected.
 */
import type { components } from "~~/types/api";

type ServerInspection = components["schemas"]["ServerInspection"];
type ServerJsonDraft = components["schemas"]["ServerJsonDraft"];
type ProtocolMode = components["schemas"]["ServerRead"]["protocol_mode"];

const emit = defineEmits<{ created: [name: string] }>();

const api = useApi();
const errorMsg = ref("");

// the names already taken, from the list the page shows
const { data: upstreams } = useUpstreams();

// ---- step 1: where the server is ----
const url = ref("");
const serverJson = ref("");
const showServerJson = ref(false);
const draft = ref<ServerJsonDraft | null>(null);
const inspecting = ref(false);
const inspection = ref<ServerInspection | null>(null);
const detailsOpen = ref(false); // the details form, after a check or on request
// what the check without a credential found; a later credential test does not change it
const detectedState = ref<string | null>(null);

// ---- step 2: what registering it takes ----
const name = ref("");
const nameEdited = ref(false); // a name typed by hand is never replaced by a suggestion
const description = ref("");
const source = ref<CredentialSource>("none");
const presetIndex = ref(0);
const headerName = ref("Authorization");
const headerValue = ref("");
const verified = ref<"" | "ok" | "refused">("");
const clientId = ref("");
const clientSecret = ref("");
const sendIdentityHeader = ref(false);
const identityHeaderTouched = ref(false); // an explicit choice outlives any default
const protocolMode = ref<ProtocolMode>("auto");
const listingSnapshot = ref("auto");
const fwdRows = ref<{ key: string; val: string }[]>([]);
const creating = ref(false);
// shown while typing, so a bad or taken name is seen before anything is sent
const nameHint = computed(() =>
  name.value.trim()
    ? nameProblem("upstream", name.value.trim(), upstreams.value.map((u) => u.name))
    : null,
);

const oauth = computed(() => inspection.value?.oauth ?? null);
/** What the server's publisher says about the header being filled in, from its server.json. */
const declaredHeaderHelp = computed(
  () =>
    draft.value?.headers?.find((h) => h.name.toLowerCase() === headerName.value.toLowerCase())
      ?.description ?? null,
);
/** The {placeholders} a server.json URL still carries, as the operator sees them. */
const urlPlaceholders = computed(() =>
  (draft.value?.url_variables ?? []).map((v) => "{" + v + "}").join(", "),
);
const isOAuth = computed(() =>
  ["per_user", "shared_oauth", "client_credentials"].includes(source.value),
);
const needsManualClient = computed(
  () =>
    source.value === "client_credentials" ||
    (isOAuth.value && oauth.value?.client_identification === "preregistered_required"),
);
const forwardsCallerToken = computed(() =>
  fwdRows.value.some((r) => r.key.trim().toLowerCase() === "authorization"),
);
const callbackUrl = computed(() => `${apiBase()}/oauth/upstream/callback`);

/** The credential source the inspection points to, which the form pre-selects. */
const DETECTED_SOURCE: Record<string, CredentialSource> = {
  ready: "none",
  oauth_required: "per_user",
  credential_required: "key",
};

function isDetected(option: CredentialSource): boolean {
  return detectedState.value !== null && DETECTED_SOURCE[detectedState.value] === option;
}

function credentialHeaders(): Record<string, string> {
  if (source.value !== "key" || !headerName.value.trim() || !headerValue.value) return {};
  const preset = CREDENTIAL_HEADER_PRESETS[presetIndex.value];
  const prefix = preset?.name && preset.name === headerName.value ? preset.prefix : "";
  const value = headerValue.value.startsWith(prefix) ? headerValue.value : prefix + headerValue.value;
  return { [headerName.value.trim()]: value };
}

function addFwdRow() {
  fwdRows.value.push({ key: "", val: "" });
}

function choosePreset(index: number) {
  presetIndex.value = index;
  const preset = CREDENTIAL_HEADER_PRESETS[index];
  if (preset?.name) headerName.value = preset.name;
}

/** Pre-select what the inspection found. */
function applyInspection(result: ServerInspection) {
  const suggestion = result.suggestion;
  if (result.suggested_url) url.value = result.suggested_url;
  suggestName(result);
  detectedState.value = result.connection_state;
  if (!identityHeaderTouched.value)
    sendIdentityHeader.value = suggestion.send_identity_header ?? false;
  const detected = DETECTED_SOURCE[result.connection_state];
  // a key already entered (from a server.json) stays chosen when the server answers anyway
  if (detected && !(detected === "none" && source.value === "key")) source.value = detected;
}

/** Take the server's own name and description, unless the operator typed their own. */
function suggestName(result: ServerInspection) {
  if (!nameEdited.value) name.value = result.suggestion.name;
  if (result.suggestion.description && !description.value)
    description.value = result.suggestion.description;
}

async function inspect(withCredential = false) {
  errorMsg.value = "";
  if (!url.value.trim()) {
    errorMsg.value = "Enter the upstream's URL first";
    return;
  }
  inspecting.value = true;
  try {
    const { data, error } = await api.POST("/api/v1/upstreams:inspect", {
      body: { url: url.value.trim(), headers: withCredential ? credentialHeaders() : {} },
    });
    if (error) {
      errorMsg.value = apiErrorMessage(error);
      return;
    }
    inspection.value = data;
    if (withCredential) {
      verified.value = data.connection_state === "ready" ? "ok" : "refused";
      suggestName(data); // the server can name itself once it lets us in
    } else {
      applyInspection(data);
    }
    detailsOpen.value = true;
  } finally {
    inspecting.value = false;
  }
}

async function importServerJson() {
  errorMsg.value = "";
  let document: Record<string, unknown>;
  try {
    document = JSON.parse(serverJson.value);
  } catch {
    errorMsg.value = "server.json is not valid JSON";
    return;
  }
  const { data, error } = await api.POST("/api/v1/upstreams:from-server-json", {
    body: { document },
  });
  if (error) {
    errorMsg.value = apiErrorMessage(error);
    return;
  }
  draft.value = data;
  name.value = data.name;
  nameEdited.value = true; // the publisher's name wins over the one serverInfo reports
  description.value = data.description ?? "";
  if (data.url) url.value = data.url;
  const headers = data.headers ?? [];
  const header = headers.find((h) => h.is_required) ?? headers[0];
  if (header) {
    source.value = "key";
    headerName.value = header.name;
    presetIndex.value = CREDENTIAL_HEADER_PRESETS.findIndex(
      (p) => p.name.toLowerCase() === header.name.toLowerCase(),
    );
    if (presetIndex.value < 0) presetIndex.value = CREDENTIAL_HEADER_PRESETS.length - 1;
  }
  showServerJson.value = false;
  if (data.url && !data.url_variables?.length) await inspect();
  else detailsOpen.value = true;
}

async function create() {
  errorMsg.value = "";
  const trimmed = name.value.trim();
  // client-side validation before submit, against the published rules and the known names
  const problem = nameProblem("upstream", trimmed, upstreams.value.map((u) => u.name));
  if (problem) {
    errorMsg.value = problem;
    return;
  }
  if (source.value === "key" && !Object.keys(credentialHeaders()).length) {
    errorMsg.value = "Enter the header name and the key or token";
    return;
  }
  if (needsManualClient.value && !clientId.value.trim()) {
    errorMsg.value = "Enter the OAuth client id the provider issued";
    return;
  }
  if (source.value === "client_credentials" && !clientSecret.value) {
    errorMsg.value = "A client-credentials client needs its client secret";
    return;
  }
  const forward_headers: Record<string, string> = {};
  for (const r of fwdRows.value) if (r.key.trim()) forward_headers[r.key.trim()] = r.val || r.key;
  creating.value = true;
  try {
    const { error } = await api.PUT("/api/v1/upstreams/{name}", {
      params: { path: { name: trimmed } },
      body: {
        name: trimmed,
        url: url.value.trim(),
        description: description.value || null,
        ...credentialSettings(source.value),
        static_headers: credentialHeaders(),
        forward_headers,
        send_identity_header: sendIdentityHeader.value,
        protocol_mode: protocolMode.value,
        listing_snapshot: listingSnapshot.value as "auto" | "shared" | "live",
      },
    });
    if (error) {
      errorMsg.value = apiErrorMessage(error);
      return;
    }
    if (needsManualClient.value) {
      const stored = await api.PUT("/api/v1/upstreams/{name}/upstream-oauth", {
        params: { path: { name: trimmed } },
        body: {
          client_id: clientId.value.trim(),
          client_secret: clientSecret.value || null,
          grant_type: source.value === "client_credentials" ? "client_credentials" : "authorization_code",
        },
      });
      if (stored.error) {
        errorMsg.value = apiErrorMessage(stored.error);
        return;
      }
    }
    if (source.value === "client_credentials") {
      const connected = await api.POST("/api/v1/upstreams/{name}/upstream-oauth:connect", {
        params: { path: { name: trimmed } },
      });
      if (connected.error) {
        errorMsg.value = apiErrorMessage(connected.error);
        return;
      }
    }
    emit("created", trimmed);
  } finally {
    creating.value = false;
  }
}

watch([headerName, headerValue, source], () => {
  verified.value = "";
});

// the same default the gateway derives — on only for its own network
watch(url, (value) => {
  if (!identityHeaderTouched.value)
    sendIdentityHeader.value = connectionKind(value).network === "local";
});
</script>

<template>
  <div class="wf-card space-y-4 max-w-2xl" data-testid="register-server">
    <h2 class="text-sm font-semibold">Register upstream server</h2>

    <p v-if="errorMsg" class="text-red-600 text-sm" data-testid="error">{{ errorMsg }}</p>

    <!-- step 1: where it is -->
    <form class="space-y-2" @submit.prevent="inspect()">
      <label class="wf-label" for="create-url">Upstream URL</label>
      <div class="flex gap-2">
        <input
          id="create-url"
          v-model="url"
          class="wf-input"
          placeholder="https://mcp.example.com/mcp"
          data-testid="create-url"
        />
        <UButton type="submit" size="sm" :loading="inspecting" data-testid="create-inspect"
          >Check</UButton
        >
      </div>
      <p class="wf-help">
        The gateway contacts the upstream and works out what it needs: whether it asks for OAuth
        sign-in, an API key, or nothing. Nothing is saved yet.
        <button
          type="button"
          class="underline"
          data-testid="create-manual"
          @click="detailsOpen = true"
        >
          Enter details without checking
        </button>
        ·
        <button
          type="button"
          class="underline"
          data-testid="create-server-json-toggle"
          @click="showServerJson = !showServerJson"
        >
          Paste a registry server.json
        </button>
      </p>
      <div v-if="showServerJson" class="space-y-2">
        <textarea
          v-model="serverJson"
          rows="6"
          class="wf-input font-mono"
          placeholder='{"name": "io.github.acme/weather", "remotes": [...]}'
          data-testid="create-server-json"
        />
        <UButton size="xs" variant="soft" data-testid="create-server-json-import" @click="importServerJson"
          >Use server.json</UButton
        >
      </div>
      <div v-if="draft && (draft.problems?.length || draft.url_variables?.length)" class="text-sm">
        <p v-for="p in draft.problems ?? []" :key="p" class="text-warning">{{ p }}</p>
        <p v-if="draft.url_variables?.length" class="text-warning">
          Replace {{ urlPlaceholders }} in the URL, then check it.
        </p>
      </div>
    </form>

    <!-- what the check found -->
    <div
      v-if="inspection"
      class="rounded-md border border-default p-3 space-y-2 text-sm"
      data-testid="inspection"
    >
      <div class="flex flex-wrap items-center gap-2">
        <UBadge
          :icon="CONNECTION_STATE_ICON[inspection.connection_state]"
          :color="connectionStateColor(inspection.connection_state)"
          variant="subtle"
          data-testid="inspection-state"
          >{{ CONNECTION_STATE_LABEL[inspection.connection_state] }}</UBadge
        >
        <span v-if="inspection.server_info" class="font-medium">
          {{ inspection.server_info.title || inspection.server_info.name }}
        </span>
        <span v-if="inspection.protocol_version" class="text-muted">
          MCP {{ inspection.protocol_version }}
        </span>
        <span v-if="inspection.tool_names?.length" class="text-muted">
          · {{ inspection.tool_names.length }}
          {{ inspection.tool_names.length === 1 ? "tool" : "tools" }}
        </span>
      </div>
      <p v-if="inspection.server_info?.description" class="text-muted">
        {{ inspection.server_info.description }}
      </p>
      <p v-if="inspection.detail" class="text-muted">{{ inspection.detail }}</p>
      <p v-if="oauth?.issuer" class="text-muted">
        Signs in at <code>{{ oauth.issuer }}</code>
        <span v-if="oauth.scopes?.length">, scopes {{ oauth.scopes.join(" ") }}</span>
      </p>
      <ul v-if="inspection.hints?.length" class="list-disc pl-5 space-y-1">
        <li v-for="h in inspection.hints" :key="h">{{ h }}</li>
      </ul>
    </div>

    <!-- step 2: what registering it takes -->
    <form v-if="detailsOpen" class="space-y-4" @submit.prevent="create">
      <div class="grid gap-3 sm:grid-cols-2">
        <div>
          <label class="wf-label" for="create-name">Name</label>
          <input
            id="create-name"
            v-model="name"
            class="wf-input"
            data-testid="create-name"
            @input="nameEdited = true"
          />
          <p v-if="nameHint" class="text-red-600 text-xs mt-1" data-testid="create-name-hint">
            {{ nameHint }}
          </p>
          <p class="wf-help">Prefixes the upstream's tools, e.g. <code>{{ name || "name" }}__search</code>.</p>
        </div>
        <div>
          <label class="wf-label" for="create-description">Description</label>
          <input
            id="create-description"
            v-model="description"
            class="wf-input"
            data-testid="create-description"
          />
        </div>
      </div>

      <fieldset class="space-y-2" data-testid="credential-source">
        <legend class="wf-label">Where does the credential come from?</legend>
        <label
          v-for="option in CREDENTIAL_SOURCES"
          :key="option.value"
          class="flex gap-2 items-start text-sm cursor-pointer"
        >
          <input
            v-model="source"
            type="radio"
            name="credential-source"
            :value="option.value"
            class="mt-1"
            :data-testid="`source-${option.value}`"
          />
          <span>
            <span class="font-medium">{{ option.label }}</span>
            <span v-if="isDetected(option.value)" class="ml-1 text-xs text-primary"
              >detected</span
            >
            <span class="block wf-help mt-0">{{ option.help }}</span>
          </span>
        </label>
      </fieldset>

      <!-- a key or token -->
      <div v-if="source === 'key'" class="space-y-2">
        <div class="grid gap-2 sm:grid-cols-3">
          <div>
            <label class="wf-label" for="create-header-preset">Header</label>
            <select
              id="create-header-preset"
              class="wf-input"
              :value="presetIndex"
              data-testid="create-header-preset"
              @change="choosePreset(Number(($event.target as HTMLSelectElement).value))"
            >
              <option v-for="(p, i) in CREDENTIAL_HEADER_PRESETS" :key="p.label" :value="i">
                {{ p.label }}
              </option>
            </select>
          </div>
          <div>
            <label class="wf-label" for="create-header-name">Header name</label>
            <input
              id="create-header-name"
              v-model="headerName"
              class="wf-input"
              data-testid="create-header-name"
            />
          </div>
          <div>
            <label class="wf-label" for="create-header-value">Key or token</label>
            <input
              id="create-header-value"
              v-model="headerValue"
              type="password"
              class="wf-input"
              autocomplete="off"
              data-testid="create-header-value"
            />
          </div>
        </div>
        <div class="flex items-center gap-2 text-sm">
          <UButton
            size="xs"
            variant="soft"
            :loading="inspecting"
            data-testid="create-verify"
            @click="inspect(true)"
            >Test the credential</UButton
          >
          <span v-if="verified === 'ok'" class="text-success">The upstream accepted it.</span>
          <span v-else-if="verified === 'refused'" class="text-error">
            The upstream refused it ({{ CONNECTION_STATE_LABEL[inspection?.connection_state ?? "error"] }}).
          </span>
        </div>
        <p v-if="declaredHeaderHelp" class="wf-help" data-testid="create-header-help">
          {{ declaredHeaderHelp }}
        </p>
        <p class="wf-help">Stored write-only: the value is never shown again.</p>
      </div>

      <!-- an OAuth client an admin must provide -->
      <div v-if="needsManualClient" class="space-y-2">
        <p class="wf-help mt-0">
          <template v-if="source === 'client_credentials'">
            Enter the client the provider issued for machine access.
          </template>
          <template v-else>
            The provider offers no automatic client registration. Register a client there with
            the redirect URI <code>{{ callbackUrl }}</code> and enter it here.
          </template>
        </p>
        <div class="grid gap-2 sm:grid-cols-2">
          <div>
            <label class="wf-label" for="create-client-id">Client ID</label>
            <input
              id="create-client-id"
              v-model="clientId"
              class="wf-input"
              data-testid="create-client-id"
            />
          </div>
          <div>
            <label class="wf-label" for="create-client-secret">Client secret</label>
            <input
              id="create-client-secret"
              v-model="clientSecret"
              type="password"
              class="wf-input"
              autocomplete="off"
              data-testid="create-client-secret"
            />
          </div>
        </div>
      </div>
      <p v-else-if="isOAuth && oauth?.client_identification" class="wf-help mt-0">
        The gateway identifies itself to the provider automatically
        ({{ oauth.client_identification === "metadata_document" ? "client metadata document" : "dynamic registration" }}).
      </p>

      <details class="text-sm" data-testid="create-advanced">
        <summary class="cursor-pointer text-muted">Advanced</summary>
        <div class="space-y-3 mt-3">
          <label class="flex gap-2 items-start">
            <input
              v-model="sendIdentityHeader"
              type="checkbox"
              class="mt-1"
              data-testid="create-send-identity-header"
              @change="identityHeaderTouched = true"
            />
            <span>
              Send the caller's identity as <code>X-MCP-User</code>
              <span class="block wf-help mt-0">
                On by default only for upstreams on the gateway's own network; a third-party
                upstream does not receive your users' ids unless you turn this on.
              </span>
            </span>
          </label>
          <div>
            <span class="wf-label">Forward client headers (client header → upstream header)</span>
            <div v-for="(row, i) in fwdRows" :key="`fwd-${i}`" class="flex gap-2 mb-1">
              <input v-model="row.key" class="wf-input" placeholder="client header" />
              <input v-model="row.val" class="wf-input" placeholder="upstream header" />
            </div>
            <UButton size="xs" variant="soft" @click="addFwdRow">Add forward header</UButton>
            <p v-if="forwardsCallerToken" class="wf-help text-warning">
              Forwarding <code>authorization</code> passes the caller's own gateway token to the
              upstream (token passthrough, which the MCP spec forbids). Prefer "A token the gateway
              issues for each caller".
            </p>
          </div>
          <div>
            <label class="wf-label" for="create-protocol-mode">Protocol</label>
            <select
              id="create-protocol-mode"
              v-model="protocolMode"
              class="wf-input"
              data-testid="create-protocol-mode"
            >
              <option value="auto">auto — negotiate (recommended)</option>
              <option value="session">session — always the initialize handshake</option>
              <option value="2026-07-28">pin 2026-07-28</option>
            </select>
          </div>
          <div>
            <label class="wf-label" for="create-listing-snapshot">Prompt and resource lists</label>
            <select
              id="create-listing-snapshot"
              v-model="listingSnapshot"
              class="wf-input"
              data-testid="create-listing-snapshot"
            >
              <option value="auto">auto — stored listing when it is the same for every caller</option>
              <option value="shared">shared — stored listing for every caller</option>
              <option value="live">live — always ask the server</option>
            </select>
            <p class="wf-help">
              Lists served from what discovery stored leave a server that scales to zero asleep
              when a client connects. Choose shared when the server is sent the caller's identity
              but lists the same prompts and resources for everyone.
            </p>
          </div>
        </div>
      </details>

      <UButton type="submit" size="sm" :loading="creating" data-testid="create-submit"
        >Create</UButton
      >
    </form>
  </div>
</template>
