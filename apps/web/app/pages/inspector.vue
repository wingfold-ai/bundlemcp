<script setup lang="ts">
import type { components } from "~~/types/api";
import { formArguments, formFields, formValues, type FormField } from "~/utils/schemaForm";
import { serverSentEvents } from "~/utils/serverSentEvents";

type Schemas = components["schemas"];
type Target = Schemas["InspectorRequest"]["target"];
type Connection = Schemas["InspectorConnection"];
type Tool = Schemas["InspectorTool"];
type Progress = Schemas["InspectorProgress"];
type Outcome = Schemas["InspectorCallOutcome"];
type Failure = Schemas["InspectorFailure"];
type Kind = "upstream" | "endpoint" | "adhoc";

const api = useApi();
const { data: upstreams } = await useUpstreams();
const { data: endpoints } = await useEndpoints();

const kind = ref<Kind>("upstream");
const upstreamName = ref("");
const endpointName = ref("");
const credential = ref("");
const adhocUrl = ref("");
const adhocHeaders = ref("");

const busy = ref(false);
const error = ref<string | null>(null);
const connection = ref<Connection | null>(null);
const tools = ref<Tool[]>([]);
const listMs = ref<number | null>(null);
const pingMs = ref<string | null>(null);
// the target the shown connection was made to; a later call reuses it, not the edited inputs
const connected = ref<Target | null>(null);

const selected = ref<Tool | null>(null);
const raw = ref(false);
const rawText = ref("{}");
const values = ref<Record<string, unknown>>({});
const calling = ref(false);
const progress = ref<Progress[]>([]);
const outcome = ref<Outcome | null>(null);
const failure = ref<Failure | null>(null);

const selectedEndpoint = computed(() => endpoints.value?.find((e) => e.name === endpointName.value));
const needsCredential = computed(() => !selectedEndpoint.value?.auth_modes?.includes("none"));
const fields = computed<FormField[] | null>(() => formFields(selected.value?.input_schema));
const destructive = computed(() => selected.value?.annotations?.destructiveHint === true);

/** Headers typed one per line as "Name: value". */
function parsedHeaders(): Record<string, string> {
  const headers: Record<string, string> = {};
  for (const line of adhocHeaders.value.split("\n")) {
    const colon = line.indexOf(":");
    if (colon <= 0) continue;
    headers[line.slice(0, colon).trim()] = line.slice(colon + 1).trim();
  }
  return headers;
}

function currentTarget(): Target | null {
  if (kind.value === "upstream") {
    return upstreamName.value ? { kind: "upstream", name: upstreamName.value } : null;
  }
  if (kind.value === "endpoint") {
    if (!endpointName.value) return null;
    return { kind: "endpoint", name: endpointName.value, credential: credential.value || null };
  }
  return adhocUrl.value ? { kind: "adhoc", url: adhocUrl.value, headers: parsedHeaders() } : null;
}

function resetResults() {
  connection.value = null;
  tools.value = [];
  listMs.value = null;
  pingMs.value = null;
  selected.value = null;
  resetCall();
}

function resetCall() {
  progress.value = [];
  outcome.value = null;
  failure.value = null;
}

async function connect() {
  const target = currentTarget();
  if (!target) return;
  busy.value = true;
  error.value = null;
  resetResults();
  try {
    const opened = await api.POST("/api/v1/inspector:connect", { body: { target } });
    if (opened.error || !opened.data) {
      error.value = apiErrorMessage(opened.error);
      return;
    }
    connection.value = opened.data;
    connected.value = target;
    const listed = await api.POST("/api/v1/inspector:list-tools", { body: { target } });
    if (listed.error || !listed.data) {
      error.value = apiErrorMessage(listed.error);
      return;
    }
    tools.value = listed.data.tools;
    listMs.value = listed.data.duration_ms;
  } finally {
    busy.value = false;
  }
}

async function ping() {
  if (!connected.value) return;
  error.value = null;
  pingMs.value = null;
  const { data, error: failed } = await api.POST("/api/v1/inspector:ping", {
    body: { target: connected.value },
  });
  if (failed || !data) {
    error.value = apiErrorMessage(failed);
    return;
  }
  pingMs.value = `${data.duration_ms} ms (connecting: ${data.initialize_ms} ms)`;
}

function selectTool(tool: Tool) {
  selected.value = tool;
  values.value = {};
  rawText.value = "{}";
  raw.value = formFields(tool.input_schema) === null;
  resetCall();
}

/** Switch between the form and raw JSON, carrying the arguments across. */
function toggleRaw() {
  const form = fields.value;
  if (!raw.value) {
    rawText.value = JSON.stringify(form ? formArguments(form, values.value) : {}, null, 2);
    raw.value = true;
    return;
  }
  if (!form) return;
  try {
    values.value = formValues(form, JSON.parse(rawText.value || "{}"));
    raw.value = false;
    error.value = null;
  } catch {
    error.value = "The raw JSON is not valid; fix it before switching back to the form.";
  }
}

function callArguments(): Record<string, unknown> | null {
  if (!raw.value && fields.value) return formArguments(fields.value, values.value);
  try {
    const parsed = JSON.parse(rawText.value || "{}");
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) return parsed;
  } catch {
    // reported below
  }
  error.value = "The arguments must be a JSON object.";
  return null;
}

async function call() {
  const tool = selected.value;
  const target = connected.value;
  if (!tool || !target) return;
  const args = callArguments();
  if (!args) return;
  if (destructive.value && !window.confirm(`"${tool.name}" says it may change or delete data. Call it?`)) {
    return;
  }
  error.value = null;
  resetCall();
  calling.value = true;
  try {
    // a POST answered with an event stream: read it with fetch, since EventSource only GETs
    const response = await fetch(`${apiBase()}/api/v1/inspector:call-tool`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify({ target, tool: tool.name, arguments: args }),
    });
    if (response.status === 401) {
      gotoLogin();
      return;
    }
    if (!response.ok || !response.body) {
      error.value = apiErrorMessage(await response.json().catch(() => null));
      return;
    }
    for await (const event of serverSentEvents(response.body)) {
      const data = JSON.parse(event.data);
      if (event.event === "progress") progress.value.push(data as Progress);
      else if (event.event === "result") outcome.value = data as Outcome;
      else if (event.event === "failure") failure.value = data as Failure;
    }
  } catch {
    error.value = "The call's stream was interrupted.";
  } finally {
    calling.value = false;
  }
}

function pretty(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

watch([kind, upstreamName, endpointName], () => {
  error.value = null;
});
</script>

<template>
  <div class="space-y-6" data-testid="inspector-page">
    <h1 class="text-lg font-semibold">Inspector</h1>
    <p class="text-sm text-toned">
      Connect to a registered upstream, one of this gateway's endpoints, or any URL, and try its tools. Stored upstream
      credentials stay on the gateway. Calls through an endpoint take its public path, so they are authenticated,
      metered and audited like any client's; calls to an upstream or a URL are only logged.
    </p>

    <div class="wf-card space-y-3" data-testid="inspector-target">
      <div class="flex gap-4 text-sm">
        <label v-for="k in ['upstream', 'endpoint', 'adhoc'] as Kind[]" :key="k" class="flex items-center gap-1">
          <input v-model="kind" type="radio" :value="k" :data-testid="`inspector-kind-${k}`" />
          {{ k === "adhoc" ? "URL" : k }}
        </label>
      </div>

      <div v-if="kind === 'upstream'">
        <label class="wf-label">Upstream</label>
        <select v-model="upstreamName" class="wf-input" data-testid="inspector-upstream">
          <option value="" disabled>choose…</option>
          <option v-for="u in upstreams" :key="u.name" :value="u.name">{{ u.name }}</option>
        </select>
      </div>

      <div v-else-if="kind === 'endpoint'" class="grid grid-cols-2 gap-3">
        <div>
          <label class="wf-label">Endpoint</label>
          <select v-model="endpointName" class="wf-input" data-testid="inspector-endpoint">
            <option value="" disabled>choose…</option>
            <option v-for="e in endpoints" :key="e.name" :value="e.name">{{ e.name }}</option>
          </select>
        </div>
        <div>
          <label class="wf-label">Credential {{ needsCredential ? "" : "(optional)" }}</label>
          <input
            v-model="credential"
            type="password"
            autocomplete="off"
            class="wf-input"
            placeholder="an API key for this endpoint, or an OAuth access token"
            data-testid="inspector-credential"
          />
          <p class="text-xs text-toned mt-1">Sent for this request only; calls are metered as this caller's.</p>
        </div>
      </div>

      <div v-else class="grid grid-cols-2 gap-3">
        <div>
          <label class="wf-label">URL</label>
          <input
            v-model="adhocUrl"
            class="wf-input"
            placeholder="https://mcp.example.com/mcp"
            data-testid="inspector-url"
          />
        </div>
        <div>
          <label class="wf-label">Headers, one per line</label>
          <textarea
            v-model="adhocHeaders"
            rows="2"
            class="wf-input font-mono"
            placeholder="Authorization: Bearer …"
            data-testid="inspector-headers"
          />
        </div>
      </div>

      <div class="flex gap-2">
        <UButton :loading="busy" :disabled="!currentTarget()" data-testid="inspector-connect" @click="connect">
          Connect
        </UButton>
        <UButton variant="outline" :disabled="!connection" data-testid="inspector-ping" @click="ping">Ping</UButton>
        <span v-if="pingMs" class="text-sm text-toned self-center" data-testid="inspector-ping-result">
          answered in {{ pingMs }}
        </span>
      </div>
    </div>

    <p v-if="error" class="text-red-600 text-sm" data-testid="error">{{ error }}</p>

    <div v-if="connection" class="wf-card space-y-2" data-testid="inspector-connection">
      <h2 class="font-medium">
        {{ connection.server_info?.title || connection.server_info?.name || "Server" }}
        <span class="text-toned text-sm">{{ connection.server_info?.version }}</span>
      </h2>
      <dl class="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-sm">
        <dt class="text-toned">Protocol revision</dt>
        <dd data-testid="inspector-protocol">{{ connection.protocol_version ?? "—" }}</dd>
        <dt class="text-toned">Capabilities</dt>
        <dd data-testid="inspector-capabilities">{{ Object.keys(connection.capabilities ?? {}).join(", ") || "none" }}</dd>
        <dt class="text-toned">Connecting took</dt>
        <dd>{{ connection.initialize_ms }} ms</dd>
      </dl>
      <p v-if="connection.instructions" class="text-sm whitespace-pre-wrap">{{ connection.instructions }}</p>
    </div>

    <div v-if="connection" class="grid grid-cols-[18rem_1fr] gap-4">
      <div class="wf-card p-0 overflow-auto max-h-[70vh]">
        <p class="text-xs text-toned px-3 pt-3">{{ tools.length }} tools, listed in {{ listMs }} ms</p>
        <ul data-testid="inspector-tools">
          <li v-for="tool in tools" :key="tool.name">
            <button
              type="button"
              class="w-full text-left px-3 py-2 text-sm hover:bg-elevated"
              :class="{ 'bg-elevated font-medium': selected?.name === tool.name }"
              :data-testid="`inspector-tool-${tool.name}`"
              @click="selectTool(tool)"
            >
              {{ tool.name }}
            </button>
          </li>
        </ul>
      </div>

      <div v-if="selected" class="wf-card space-y-3" data-testid="inspector-tool">
        <div>
          <h2 class="font-medium">{{ selected.title || selected.name }}</h2>
          <p v-if="selected.description" class="text-sm text-toned whitespace-pre-wrap">{{ selected.description }}</p>
          <div v-if="selected.annotations" class="flex gap-2 mt-1">
            <UBadge v-for="(v, k) in selected.annotations" :key="k" variant="subtle" :color="v === true ? 'primary' : 'neutral'">
              {{ k }}: {{ v }}
            </UBadge>
          </div>
        </div>

        <details>
          <summary class="text-sm cursor-pointer">Input schema</summary>
          <pre class="text-xs overflow-auto" data-testid="inspector-schema">{{ pretty(selected.input_schema) }}</pre>
        </details>

        <div class="flex items-center gap-2">
          <h3 class="text-sm font-medium">Arguments</h3>
          <UButton size="xs" variant="ghost" :disabled="!fields" data-testid="inspector-raw-toggle" @click="toggleRaw">
            {{ raw ? "Form" : "Raw JSON" }}
          </UButton>
          <span v-if="!fields" class="text-xs text-toned">this schema needs raw JSON</span>
        </div>

        <textarea
          v-if="raw || !fields"
          v-model="rawText"
          rows="6"
          class="wf-input font-mono text-xs"
          data-testid="inspector-raw"
        />
        <div v-else class="space-y-2">
          <p v-if="!fields.length" class="text-sm text-toned">This tool takes no arguments.</p>
          <div v-for="field in fields" :key="field.name">
            <label class="wf-label">
              {{ field.name }}<span v-if="field.required" class="text-red-600"> *</span>
              <span class="text-toned font-normal"> {{ field.kind }}</span>
            </label>
            <select
              v-if="field.kind === 'enum'"
              v-model="values[field.name]"
              class="wf-input"
              :data-testid="`inspector-arg-${field.name}`"
            >
              <option v-for="o in field.options" :key="String(o)" :value="String(o)">{{ o }}</option>
            </select>
            <input
              v-else-if="field.kind === 'boolean'"
              v-model="values[field.name]"
              type="checkbox"
              :data-testid="`inspector-arg-${field.name}`"
            />
            <input
              v-else
              v-model="values[field.name]"
              :type="field.kind === 'string' ? 'text' : 'number'"
              :required="field.required"
              class="wf-input"
              :data-testid="`inspector-arg-${field.name}`"
            />
            <p v-if="field.description" class="text-xs text-toned">{{ field.description }}</p>
          </div>
        </div>

        <UButton :loading="calling" :color="destructive ? 'error' : 'primary'" data-testid="inspector-call" @click="call">
          Call {{ selected.name }}
        </UButton>

        <ol v-if="progress.length" class="text-sm space-y-1" data-testid="inspector-progress">
          <li v-for="(p, i) in progress" :key="i" data-testid="inspector-progress-item">
            <span class="tabular-nums text-toned">+{{ p.elapsed_ms }} ms</span>
            {{ p.progress }}<span v-if="p.total != null">/{{ p.total }}</span>
            <span v-if="p.message"> — {{ p.message }}</span>
          </li>
        </ol>

        <div v-if="failure" class="text-sm text-red-600" data-testid="inspector-failure">
          {{ failure.connection_state }}: {{ failure.detail }}
        </div>

        <div v-if="outcome" data-testid="inspector-outcome" :data-error="outcome.is_error">
          <p class="text-sm" :class="outcome.is_error ? 'text-red-600' : 'text-toned'">
            {{ outcome.is_error ? "Error" : "Result" }} in
            <span data-testid="inspector-duration">{{ outcome.duration_ms }} ms</span>
            (connecting: {{ outcome.initialize_ms }} ms)
          </p>
          <p v-if="outcome.error_message" class="text-sm text-red-600" data-testid="inspector-error">
            {{ outcome.error_code }}: {{ outcome.error_message }}
          </p>
          <pre v-if="outcome.result" class="text-xs overflow-auto max-h-96" data-testid="inspector-result">{{ pretty(outcome.result) }}</pre>
        </div>
      </div>
    </div>
  </div>
</template>
