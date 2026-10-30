<script setup lang="ts">
/**
 * Guided server registration: start from the URL, let the gateway inspect
 * it, and ask only what the upstream cannot answer — where the credential
 * comes from — with the detected answer pre-selected.
 */
import type { components } from "~~/types/api";

type Schemas = components["schemas"];

const emit = defineEmits<{ created: [name: string] }>();

const api = useApi();

// the names already taken, from the list the page shows
const { data: upstreams } = useUpstreams();

// ---- step 2: what registering it takes ----
const name = ref("");
const nameEdited = ref(false);
const description = ref("");
const source = ref<CredentialSource>("none");
const presetIndex = ref(0);
const headerName = ref("Authorization");
const headerValue = ref("");
const clientId = ref("");
const clientSecret = ref("");
const sendIdentityHeader = ref(false);
const identityHeaderTouched = ref(false);
const protocolMode = ref<Schemas["ServerRead"]["protocol_mode"]>("auto");
const listingSnapshot = ref<Schemas["ListingSnapshotMode"]>("auto");
const fwdRows = ref<HeaderRow[]>([]);
const creating = ref(false);

function credentialHeaders(): Record<string, string> {
  if (source.value !== "key" || !headerName.value.trim() || !headerValue.value) return {};
  const preset = CREDENTIAL_HEADER_PRESETS[presetIndex.value];
  const prefix = preset?.name && preset.name === headerName.value ? preset.prefix : "";
  const value = headerValue.value.startsWith(prefix) ? headerValue.value : prefix + headerValue.value;
  return { [headerName.value.trim()]: value };
}

// ---- step 1: where the server is ----
// one object, so the template reads its fields as the inspection's own
const check = reactive(useServerInspection({
  name, nameEdited, description, source, headerName, presetIndex,
  sendIdentityHeader, identityHeaderTouched, credentialHeaders,
}));

// shown while typing, so a bad or taken name is seen before anything is sent
const nameHint = computed(() =>
  name.value.trim()
    ? nameProblem("upstream", name.value.trim(), upstreams.value.map((u) => u.name))
    : null,
);

/** What the server's publisher says about the header being filled in, from its server.json. */
const declaredHeaderHelp = computed(
  () =>
    check.draft?.headers?.find((h) => h.name.toLowerCase() === headerName.value.toLowerCase())
      ?.description ?? null,
);
/** The {placeholders} a server.json URL still carries, as the operator sees them. */
const urlPlaceholders = computed(() =>
  (check.draft?.url_variables ?? []).map((v) => "{" + v + "}").join(", "),
);
const needsManualClient = computed(
  () =>
    source.value === "client_credentials" ||
    (["per_user", "shared_oauth"].includes(source.value) &&
      check.inspection?.oauth?.client_identification === "preregistered_required"),
);
const forwardsCallerToken = computed(() =>
  fwdRows.value.some((r) => r.key.trim().toLowerCase() === "authorization"),
);

// the card's one error, whichever of its steps failed last
const { run, error } = useCardAction();

/** Store the upstream, then the OAuth client it needs, then connect a machine client. */
async function register(trimmed: string) {
  // client-side validation before submit, against the published rules and the known names
  const problem = nameProblem("upstream", trimmed, upstreams.value.map((u) => u.name));
  if (problem) throw new ValidationProblem(problem);
  if (source.value === "key" && !Object.keys(credentialHeaders()).length) {
    throw new ValidationProblem("Enter the header name and the key or token");
  }
  if (needsManualClient.value && !clientId.value.trim()) {
    throw new ValidationProblem("Enter the OAuth client id the provider issued");
  }
  if (source.value === "client_credentials" && !clientSecret.value) {
    throw new ValidationProblem("A client-credentials client needs its client secret");
  }
  const stored = await api.PUT("/api/v1/upstreams/{name}", {
    params: { path: { name: trimmed } },
    body: {
      name: trimmed,
      url: check.url.trim(),
      description: description.value || null,
      ...credentialSettings(source.value),
      static_headers: credentialHeaders(),
      forward_headers: rowsToHeaders(fwdRows.value, { emptyValue: "key" }),
      send_identity_header: sendIdentityHeader.value,
      protocol_mode: protocolMode.value,
      listing_snapshot: listingSnapshot.value,
    },
  });
  if (stored.error || !needsManualClient.value) return stored;
  const client = await api.PUT("/api/v1/upstreams/{name}/upstream-oauth", {
    params: { path: { name: trimmed } },
    body: {
      client_id: clientId.value.trim(),
      client_secret: clientSecret.value || null,
      grant_type: source.value === "client_credentials" ? "client_credentials" : "authorization_code",
    },
  });
  if (client.error || source.value !== "client_credentials") return client;
  return await api.POST("/api/v1/upstreams/{name}/upstream-oauth:connect", {
    params: { path: { name: trimmed } },
  });
}

async function create() {
  const trimmed = name.value.trim();
  creating.value = true;
  try {
    if (await run(() => register(trimmed))) emit("created", trimmed);
  } finally {
    creating.value = false;
  }
}

watch([headerName, headerValue, source], () => {
  check.verified = "";
});

// the same default the gateway derives — on only for its own network
watch(() => check.url, (value) => {
  if (!identityHeaderTouched.value)
    sendIdentityHeader.value = connectionKind(value).network === "local";
});
</script>

<template>
  <div class="wf-card space-y-4 max-w-2xl" data-testid="register-server">
    <h2 class="text-sm font-semibold">Register upstream server</h2>

    <p v-if="error" class="text-red-600 text-sm" data-testid="error">{{ error }}</p>

    <!-- step 1: where it is -->
    <form class="space-y-2" @submit.prevent="run(() => check.inspect())">
      <label class="wf-label" for="create-url">Upstream URL</label>
      <div class="flex gap-2">
        <input
          id="create-url"
          v-model="check.url"
          class="wf-input"
          placeholder="https://mcp.example.com/mcp"
          data-testid="create-url"
        />
        <UButton type="submit" size="sm" :loading="check.inspecting" data-testid="create-inspect"
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
          @click="check.detailsOpen = true"
        >
          Enter details without checking
        </button>
        ·
        <button
          type="button"
          class="underline"
          data-testid="create-server-json-toggle"
          @click="check.showServerJson = !check.showServerJson"
        >
          Paste a registry server.json
        </button>
      </p>
      <div v-if="check.showServerJson" class="space-y-2">
        <textarea
          v-model="check.serverJson"
          rows="6"
          class="wf-input font-mono"
          placeholder='{"name": "io.github.acme/weather", "remotes": [...]}'
          data-testid="create-server-json"
        />
        <UButton size="xs" variant="soft" data-testid="create-server-json-import" @click="run(check.importServerJson)"
          >Use server.json</UButton
        >
      </div>
      <div v-if="check.draft?.problems?.length || check.draft?.url_variables?.length" class="text-sm">
        <p v-for="p in check.draft?.problems ?? []" :key="p" class="text-warning">{{ p }}</p>
        <p v-if="check.draft?.url_variables?.length" class="text-warning">
          Replace {{ urlPlaceholders }} in the URL, then check it.
        </p>
      </div>
    </form>

    <!-- what the check found -->
    <InspectionSummary v-if="check.inspection" :inspection="check.inspection" />

    <!-- step 2: what registering it takes -->
    <form v-if="check.detailsOpen" class="space-y-4" @submit.prevent="create">
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

      <CredentialSourcePicker
        v-model:source="source"
        v-model:preset-index="presetIndex"
        v-model:header-name="headerName"
        v-model:header-value="headerValue"
        v-model:client-id="clientId"
        v-model:client-secret="clientSecret"
        :detected="check.detectedSource"
        :inspection="check.inspection"
        :verified="check.verified"
        :verifying="check.inspecting"
        :needs-manual-client="needsManualClient"
        :header-help="declaredHeaderHelp"
        @verify="run(() => check.inspect(true))"
      />

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
            <HeaderRowsEditor
              v-model="fwdRows"
              key-placeholder="client header"
              value-placeholder="upstream header"
              add-label="Add forward header"
            />
            <p v-if="forwardsCallerToken" class="wf-help text-warning">
              Forwarding <code>authorization</code> passes the caller's own gateway token to the
              upstream (token passthrough, which the MCP spec forbids). Prefer "A token the gateway
              issues for each caller".
            </p>
          </div>
          <UpstreamProtocolSettings
            v-model:protocol-mode="protocolMode"
            v-model:listing-snapshot="listingSnapshot"
            id-prefix="create"
          />
        </div>
      </details>

      <UButton type="submit" size="sm" :loading="creating" data-testid="create-submit"
        >Create</UButton
      >
    </form>
  </div>
</template>
