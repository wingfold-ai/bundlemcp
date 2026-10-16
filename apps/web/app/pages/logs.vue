<script setup lang="ts">
import type { components } from "~~/types/api";

type LiveLogEntry = components["schemas"]["LiveLogEntry"];
type Level = "debug" | "info" | "warning" | "error" | "critical";
type StreamState = "connecting" | "live" | "paused" | "reconnecting" | "disconnected";

// the page holds a window onto the tail, not the whole buffer
const MAX_ROWS = 1000;
const BACKFILL = 200;
// a stream the browser gave up on (refused, or the gateway gone) is reopened after this long
const RETRY_MS = 5000;

const api = useApi();
const { data: upstreams } = await useUpstreams();
const { data: endpoints } = await useEndpoints();

const level = ref<Level | "all">("all");
const text = ref("");
const upstream = ref("");
const endpoint = ref("");

const rows = ref<LiveLogEntry[]>([]);
const seen = new Set<string>();
const lastId = ref<string | null>(null);
const state = ref<StreamState>("connecting");
const paused = ref(false);
const loadError = ref<string | null>(null);

let source: EventSource | null = null;
let retryTimer: ReturnType<typeof setTimeout> | null = null;
// bumped by every restart, so a backfill that answers after the filters changed is dropped
let generation = 0;

type LogQuery = { level?: Level; q?: string; upstream?: string; endpoint?: string };

function filters(): LogQuery {
  const query: LogQuery = {};
  if (level.value !== "all") query.level = level.value;
  if (text.value.trim()) query.q = text.value.trim();
  if (upstream.value) query.upstream = upstream.value;
  if (endpoint.value) query.endpoint = endpoint.value;
  return query;
}

const scroller = ref<HTMLElement | null>(null);
// follow the tail until the admin scrolls up to read; scrolling back down follows again
const following = ref(true);

function onScroll() {
  const el = scroller.value;
  if (!el) return;
  following.value = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
}

async function scrollToTail() {
  if (!following.value) return;
  await nextTick();
  const el = scroller.value;
  if (el) el.scrollTop = el.scrollHeight;
}

/** Append entries in arrival order, skipping any already shown, and trim the oldest. */
function append(entries: LiveLogEntry[]) {
  let added = false;
  for (const entry of entries) {
    if (!entry.id || seen.has(entry.id)) continue;
    seen.add(entry.id);
    rows.value.push(entry);
    lastId.value = entry.id;
    added = true;
  }
  if (!added) return;
  const excess = rows.value.length - MAX_ROWS;
  if (excess > 0) {
    for (const dropped of rows.value.splice(0, excess)) seen.delete(dropped.id!);
  }
  void scrollToTail();
}

function closeStream() {
  if (retryTimer) clearTimeout(retryTimer);
  retryTimer = null;
  source?.close();
  source = null;
}

/** Follow new entries, after `since` when given, otherwise from now on. */
function openStream(since: string | null) {
  closeStream();
  const query = new URLSearchParams(filters() as Record<string, string>);
  if (since) query.set("since", since);
  const es = new EventSource(`${apiBase()}/api/v1/logs/stream?${query}`, {
    withCredentials: true,
  });
  source = es;
  state.value = "connecting";
  es.onopen = () => {
    state.value = "live";
  };
  es.onmessage = (event: MessageEvent<string>) => {
    try {
      append([JSON.parse(event.data) as LiveLogEntry]);
    } catch {
      // a malformed event is skipped; the next one still arrives
    }
  };
  es.onerror = () => {
    if (source !== es) return;
    if (es.readyState === EventSource.CLOSED) {
      // the browser stopped retrying (a refusal such as too many streams); try again later
      state.value = "disconnected";
      retryTimer = setTimeout(() => {
        if (source === es && !paused.value) openStream(lastId.value);
      }, RETRY_MS);
    } else {
      // the browser reconnects by itself and resumes from the last event id it saw
      state.value = "reconnecting";
    }
  };
}

/** Clear the view, load the newest matching entries, then follow from the last of them. */
async function restart() {
  const mine = ++generation;
  closeStream();
  rows.value = [];
  seen.clear();
  lastId.value = null;
  loadError.value = null;
  following.value = true;
  if (paused.value) {
    state.value = "paused";
    return;
  }
  state.value = "connecting";
  // a live tail, not cached management data: always fetched fresh, never through the query layer
  const { data, error } = await api.GET("/api/v1/logs", {
    params: { query: { ...filters(), limit: BACKFILL } },
  });
  if (mine !== generation) return;
  if (error || !data) {
    loadError.value = "The recent log entries could not be loaded.";
  } else {
    append(data);
  }
  if (!paused.value) openStream(lastId.value);
}

function togglePause() {
  if (paused.value) {
    paused.value = false;
    // nothing shown yet means no position to resume from; load what matches now instead
    if (lastId.value) openStream(lastId.value);
    else void restart();
  } else {
    paused.value = true;
    closeStream();
    state.value = "paused";
  }
}

let textTimer: ReturnType<typeof setTimeout> | null = null;
watch([level, upstream, endpoint], () => void restart());
watch(text, () => {
  if (textTimer) clearTimeout(textTimer);
  textTimer = setTimeout(() => void restart(), 400);
});

onMounted(() => void restart());
onBeforeUnmount(() => {
  generation++;
  if (textTimer) clearTimeout(textTimer);
  closeStream();
});

const expanded = ref(new Set<string>());
function toggleFields(id: string) {
  const next = new Set(expanded.value);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  expanded.value = next;
}

function levelColor(value: string): "neutral" | "info" | "warning" | "error" {
  const severity = value.toLowerCase();
  if (severity === "info") return "info";
  if (severity === "warning") return "warning";
  if (severity === "error" || severity === "critical") return "error";
  return "neutral";
}

const pad = (n: number, width = 2) => String(n).padStart(width, "0");
function clock(timestamp: string): string {
  const d = new Date(timestamp);
  if (Number.isNaN(d.getTime())) return timestamp;
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}.${pad(d.getMilliseconds(), 3)}`;
}

const stateColor = computed(() => {
  if (state.value === "live") return "success";
  if (state.value === "paused") return "neutral";
  if (state.value === "disconnected") return "error";
  return "warning";
});
</script>

<template>
  <div class="space-y-6" data-testid="logs-page">
    <div class="flex items-center gap-3">
      <h1 class="text-lg font-semibold">Live logs</h1>
      <UBadge :color="stateColor" variant="subtle" data-testid="logs-state">{{ state }}</UBadge>
      <UButton
        class="ml-auto"
        variant="outline"
        :icon="paused ? 'i-lucide-play' : 'i-lucide-pause'"
        data-testid="logs-pause"
        @click="togglePause"
      >
        {{ paused ? "Resume" : "Pause" }}
      </UButton>
    </div>

    <p class="text-sm text-toned" data-testid="logs-info">
      A live view of the gateway's newest events, about the latest 10,000 across all replicas. It is not kept: older
      entries drop out as new ones arrive, and the view empties when the gateway's live store restarts. For history,
      use the log stack of your container platform; tool calls are also in the audit log.
    </p>

    <p v-if="loadError" class="text-red-600 text-sm" data-testid="error">{{ loadError }}</p>

    <div class="wf-card">
      <div class="grid grid-cols-4 gap-3">
        <div>
          <label class="wf-label">Level (and above)</label>
          <select v-model="level" class="wf-input" data-testid="logs-level">
            <option value="all">all</option>
            <option value="debug">debug</option>
            <option value="info">info</option>
            <option value="warning">warning</option>
            <option value="error">error</option>
            <option value="critical">critical</option>
          </select>
        </div>
        <div>
          <label class="wf-label">Text</label>
          <input
            v-model="text"
            class="wf-input"
            placeholder="event or field contains…"
            data-testid="logs-text"
          />
        </div>
        <div>
          <label class="wf-label">Upstream</label>
          <select v-model="upstream" class="wf-input" data-testid="logs-upstream">
            <option value="">any</option>
            <option v-for="u in upstreams" :key="u.name" :value="u.name">{{ u.name }}</option>
          </select>
        </div>
        <div>
          <label class="wf-label">Endpoint</label>
          <select v-model="endpoint" class="wf-input" data-testid="logs-endpoint">
            <option value="">any</option>
            <option v-for="e in endpoints" :key="e.name" :value="e.name">{{ e.name }}</option>
          </select>
        </div>
      </div>
    </div>

    <p class="text-sm text-gray-500" data-testid="logs-count">
      {{ rows.length }} entries shown<span v-if="rows.length >= MAX_ROWS">, the newest {{ MAX_ROWS }}</span>
      <span v-if="!following">; scrolled up, so new entries are not followed</span>
    </p>

    <div
      ref="scroller"
      class="overflow-auto max-h-[65vh] border border-default rounded"
      data-testid="logs-scroller"
      @scroll="onScroll"
    >
      <table class="wf-table" data-testid="logs-table">
        <thead class="sticky top-0 bg-default">
          <tr>
            <th>Time</th>
            <th>Level</th>
            <th>Replica</th>
            <th>Endpoint</th>
            <th>Upstream</th>
            <th>Event</th>
            <th>Fields</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="entry in rows" :key="entry.id">
            <tr data-testid="log-row" :data-log-id="entry.id">
              <td class="whitespace-nowrap tabular-nums" :title="entry.timestamp">
                {{ clock(entry.timestamp) }}
              </td>
              <td>
                <UBadge
                  :color="levelColor(entry.level)"
                  :variant="entry.level.toLowerCase() === 'critical' ? 'solid' : 'subtle'"
                >
                  {{ entry.level.toLowerCase() }}
                </UBadge>
              </td>
              <td class="whitespace-nowrap">{{ entry.replica }}</td>
              <td class="whitespace-nowrap">{{ entry.endpoint ?? "" }}</td>
              <td class="whitespace-nowrap">{{ entry.upstream ?? "" }}</td>
              <td class="break-all font-mono text-xs" data-testid="log-event">{{ entry.event }}</td>
              <td>
                <UButton
                  v-if="entry.fields && Object.keys(entry.fields).length"
                  size="xs"
                  variant="ghost"
                  :icon="expanded.has(entry.id!) ? 'i-lucide-chevron-down' : 'i-lucide-chevron-right'"
                  data-testid="log-fields-toggle"
                  @click="toggleFields(entry.id!)"
                >
                  {{ Object.keys(entry.fields).length }}
                </UButton>
              </td>
            </tr>
            <tr v-if="expanded.has(entry.id!)">
              <td colspan="7">
                <pre class="text-xs whitespace-pre-wrap break-all" data-testid="log-fields">{{
                  JSON.stringify(entry.fields, null, 2)
                }}</pre>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
      <p v-if="!rows.length" class="text-sm text-muted p-3" data-testid="logs-empty">
        No entries match yet; new ones appear here as the gateway logs them.
      </p>
    </div>
  </div>
</template>
