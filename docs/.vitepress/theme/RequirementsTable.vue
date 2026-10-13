<script setup lang="ts">
/**
 * Every requirement in full — text, scenarios, status and dates — grouped by slice and
 * filterable by slice, status and free text. The data is /requirements.json, built from
 * openspec/ by ../requirements-ledger.ts with the Markdown already rendered.
 */
import { computed, nextTick, onMounted, ref, watch } from "vue";
import { withBase } from "vitepress";
import type { Ledger, LedgerRequirement, Slice } from "../requirements-ledger";

type Status = "all" | "active" | "proposed" | "retired";

const slice = ref("all");
const status = ref<Status>("all");
const query = ref("");
const showScenarios = ref(false);
const loadError = ref("");
const data = ref<Ledger>({
  slices: [],
  retired_codes: [],
  former_codes: {},
  migrated_on: "",
  requirements: [],
});

const sliceByCode = computed(() => new Map(data.value.slices.map((s) => [s.code, s])));

// ?slice=BND&status=proposed opens the page filtered; #<code> jumps to one requirement.
onMounted(async () => {
  try {
    const res = await fetch(withBase("/requirements.json"));
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    data.value = (await res.json()) as Ledger;
  } catch (e) {
    loadError.value = `Could not load the requirements (${e}).`;
    return;
  }
  const params = new URLSearchParams(window.location.search);
  const wanted = params.get("slice");
  if (wanted && sliceByCode.value.has(wanted)) slice.value = wanted;
  const wantedStatus = params.get("status");
  if (wantedStatus && ["active", "proposed", "retired"].includes(wantedStatus))
    status.value = wantedStatus as Status;
  if (window.location.hash) {
    await nextTick();
    const target = document.getElementById(decodeURIComponent(window.location.hash.slice(1)));
    target?.scrollIntoView();
  }
});

watch([slice, status], () => {
  const params = new URLSearchParams();
  if (slice.value !== "all") params.set("slice", slice.value);
  if (status.value !== "all") params.set("status", status.value);
  const search = params.toString();
  history.replaceState(null, "", search ? `?${search}` : window.location.pathname);
});

function counts(code: string) {
  const reqs = data.value.requirements.filter((r) => r.code === code);
  return {
    active: reqs.filter((r) => r.status === "active").length,
    proposed: reqs.filter((r) => r.status === "proposed").length,
  };
}

const rows = computed(() => {
  const q = query.value.trim().toLowerCase();
  return data.value.requirements.filter(
    (r) =>
      (slice.value === "all" || r.code === slice.value) &&
      (status.value === "all" || r.status === status.value) &&
      (!q || r.search.includes(q)),
  );
});

// The filtered requirements, in registry order of their slices.
const sections = computed(() =>
  data.value.slices
    .map((s) => ({ slice: s, reqs: rows.value.filter((r) => r.code === s.code) }))
    .filter((section) => section.reqs.length > 0),
);

const selected = computed<Slice | undefined>(() => sliceByCode.value.get(slice.value));

function since(r: LedgerRequirement): string {
  if (r.status === "proposed") return "not yet";
  return r.active_since ?? r.active_since_note ?? "—";
}

function specUrl(s: Slice): string {
  return `https://github.com/wingfold-ai/bundlemcp/blob/main/openspec/specs/${s.capability}/spec.md`;
}

function changeUrl(change: string): string {
  return `https://github.com/wingfold-ai/bundlemcp/tree/main/openspec/changes/${change}`;
}
</script>

<template>
  <p v-if="loadError" class="req-summary">{{ loadError }}</p>
  <p v-else-if="!data.requirements.length" class="req-summary">Loading requirements…</p>
  <div v-if="slice === 'all' && !query" class="req-slices">
    <button
      v-for="s in data.slices"
      :key="s.code"
      class="req-slice-card"
      type="button"
      :data-testid="`req-slice-card-${s.code}`"
      @click="slice = s.code"
    >
      <span class="req-code-badge">{{ s.code }}</span>
      <strong>{{ s.title }}</strong>
      <span class="req-slice-summary">{{ s.summary }}</span>
      <span class="req-slice-counts">
        {{ counts(s.code).active }} active<template v-if="counts(s.code).proposed">
          · {{ counts(s.code).proposed }} proposed</template
        >
      </span>
    </button>
  </div>

  <div class="req-filters">
    <label>
      Slice
      <select v-model="slice" data-testid="req-slice">
        <option value="all">All slices</option>
        <option v-for="s in data.slices" :key="s.code" :value="s.code">
          {{ s.code }} — {{ s.title }}
        </option>
      </select>
    </label>
    <label>
      Status
      <select v-model="status" data-testid="req-status">
        <option value="all">All</option>
        <option value="active">Active</option>
        <option value="proposed">Proposed</option>
        <option value="retired">Retired</option>
      </select>
    </label>
    <label class="req-search">
      Search
      <input
        v-model="query"
        type="search"
        placeholder="Code (also a former one), name or text"
        data-testid="req-search"
      />
    </label>
    <label class="req-toggle">
      <input v-model="showScenarios" type="checkbox" data-testid="req-scenarios" />
      Expand scenarios
    </label>
  </div>

  <div v-if="selected" class="req-selected" data-testid="req-selected-slice">
    <h2 :id="`slice-${selected.code}`">
      <span class="req-code-badge">{{ selected.code }}</span> {{ selected.title }}
    </h2>
    <p>
      <strong>{{ selected.summary }}</strong> {{ selected.description }}
    </p>
    <p class="req-boundary"><em>Not here:</em> {{ selected.boundary }}</p>
    <p class="req-meta">
      {{ counts(selected.code).active }} active, {{ counts(selected.code).proposed }} proposed ·
      <a :href="specUrl(selected)" target="_blank" rel="noopener">specification</a> ·
      <a href="#" @click.prevent="slice = 'all'">all slices</a>
    </p>
  </div>

  <p class="req-summary">{{ rows.length }} requirement{{ rows.length === 1 ? "" : "s" }} shown</p>

  <section v-for="section in sections" :key="section.slice.code" class="req-section">
    <h2 v-if="!selected" :id="`slice-${section.slice.code}`" class="req-section-title">
      <span class="req-code-badge">{{ section.slice.code }}</span> {{ section.slice.title }}
      <small>{{ section.slice.summary }}</small>
    </h2>

    <article
      v-for="r in section.reqs"
      :id="r.id"
      :key="r.id"
      class="req-card"
      :data-testid="`req-${r.id}`"
    >
      <header>
        <a class="req-id" :href="`#${r.id}`">{{ r.id }}</a>
        <span class="req-name">{{ r.name }}</span>
        <span :class="['req-badge', `req-${r.status}`]">{{ r.status }}</span>
      </header>
      <p class="req-meta">
        Specified {{ r.specified ?? "—" }} · active since {{ since(r) }}
        <template v-if="r.last_changed"> · last changed {{ r.last_changed }}</template>
        <template v-if="r.former_ids.length"> · was {{ r.former_ids.join(", ") }}</template>
        <template v-if="r.url">
          · <a :href="r.url" target="_blank" rel="noopener">source</a></template
        >
      </p>
      <p v-if="r.open_changes.length" class="req-meta req-changes">
        <span v-for="c in r.open_changes" :key="c.change + c.op">
          {{ c.op === "ADDED" ? "proposed in" : `${c.op.toLowerCase()} by` }}
          <a :href="changeUrl(c.change)" target="_blank" rel="noopener">{{ c.change }}</a>
        </span>
      </p>
      <!-- eslint-disable-next-line vue/no-v-html -- rendered at build time from the repository's own specs -->
      <div class="req-body vp-doc" v-html="r.html" />
      <details
        v-for="sc in r.scenarios"
        :key="sc.name"
        class="req-scenario"
        :open="showScenarios"
      >
        <summary>Scenario: {{ sc.name }}</summary>
        <!-- eslint-disable-next-line vue/no-v-html -->
        <div class="vp-doc" v-html="sc.html" />
      </details>
    </article>
  </section>
</template>

<style scoped>
.req-slices {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 10px;
  margin: 20px 0;
}
.req-slice-card {
  display: flex;
  flex-direction: column;
  gap: 4px;
  text-align: left;
  border: 1px solid var(--vp-c-divider);
  border-radius: 8px;
  padding: 10px 12px;
  background: var(--vp-c-bg-soft);
  cursor: pointer;
  font-size: 14px;
}
.req-slice-card:hover {
  border-color: var(--vp-c-brand-1);
}
.req-slice-summary {
  color: var(--vp-c-text-2);
  font-size: 13px;
  line-height: 1.4;
}
.req-slice-counts {
  color: var(--vp-c-text-3);
  font-size: 12px;
}
.req-code-badge {
  display: inline-block;
  font-family: var(--vp-font-family-mono);
  font-size: 12px;
  font-weight: 600;
  color: var(--vp-c-brand-1);
  background: var(--vp-c-brand-soft);
  border-radius: 4px;
  padding: 0 6px;
  width: fit-content;
}
.req-filters {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 12px;
  margin: 16px 0 8px;
}
.req-filters label {
  display: flex;
  flex-direction: column;
  font-size: 13px;
  color: var(--vp-c-text-2);
  gap: 4px;
}
.req-filters label.req-toggle {
  flex-direction: row;
  align-items: center;
  gap: 6px;
}
.req-filters select,
.req-filters input[type="search"] {
  border: 1px solid var(--vp-c-divider);
  border-radius: 6px;
  padding: 4px 8px;
  background: var(--vp-c-bg);
  color: var(--vp-c-text-1);
  font-size: 14px;
}
.req-search {
  flex: 1;
  min-width: 180px;
}
.req-selected {
  border-left: 3px solid var(--vp-c-brand-1);
  padding: 4px 0 4px 14px;
  margin: 16px 0;
}
.req-selected h2,
.req-section-title {
  border-top: none;
  margin: 24px 0 8px;
  padding-top: 0;
}
.req-section-title small {
  display: block;
  font-size: 14px;
  font-weight: 400;
  color: var(--vp-c-text-2);
}
.req-boundary {
  color: var(--vp-c-text-2);
  font-size: 14px;
}
.req-summary {
  font-size: 13px;
  color: var(--vp-c-text-2);
}
.req-card {
  border: 1px solid var(--vp-c-divider);
  border-radius: 8px;
  padding: 12px 16px;
  margin: 12px 0;
  scroll-margin-top: 80px;
}
.req-card header {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 8px;
}
.req-id {
  font-family: var(--vp-font-family-mono);
  font-weight: 600;
}
.req-name {
  font-weight: 600;
  flex: 1;
}
.req-meta {
  font-size: 12px;
  color: var(--vp-c-text-2);
  margin: 4px 0;
}
.req-changes span + span::before {
  content: " · ";
}
.req-body {
  font-size: 14px;
}
.req-body :deep(p) {
  margin: 8px 0;
}
.req-scenario {
  font-size: 13px;
  margin: 4px 0;
}
.req-scenario summary {
  cursor: pointer;
  color: var(--vp-c-text-2);
}
.req-scenario :deep(ul) {
  margin: 4px 0;
}
.req-badge {
  border-radius: 10px;
  padding: 1px 8px;
  font-size: 12px;
  white-space: nowrap;
}
.req-active {
  background: var(--vp-c-green-soft);
  color: var(--vp-c-green-1);
}
.req-proposed {
  background: var(--vp-c-yellow-soft);
  color: var(--vp-c-yellow-1);
}
.req-retired {
  background: var(--vp-c-gray-soft);
  color: var(--vp-c-text-2);
}
</style>
