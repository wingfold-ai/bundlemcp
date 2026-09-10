<script setup lang="ts">
import { withBase } from "vitepress";

const servers = [
  { name: "weather", tools: ["forecast", "current"] },
  { name: "notes", tools: ["search", "create"] },
  { name: "crm", tools: ["lookup", "update"] },
];

const bundleTools = [
  { name: "weather__forecast" },
  { name: "weather__current" },
  { name: "notes__search" },
  { name: "add_note", from: "notes__create" },
  { name: "crm__lookup" },
  { name: "crm__update", disabled: true },
];

const endpoints = [
  { path: "/assistant/mcp", client: "claude.ai", auth: "OAuth 2.1", note: "profile: claude" },
  { path: "/assistant-gpt/mcp", client: "ChatGPT", auth: "OAuth 2.1", note: "profile: chatgpt, tools re-annotated read-only" },
  { path: "/assistant-ci/mcp", client: "scripts & agents", auth: "API key", note: "profile: default, 120 calls/min per key" },
];
</script>

<template>
  <section class="pipeline">
    <div class="card">
      <div class="col">
        <h3>Upstream MCP servers</h3>
        <p class="hint">Streamable HTTP, probed and cached</p>
        <div v-for="s in servers" :key="s.name" class="node">
          <div class="title">{{ s.name }}</div>
          <div class="chips">
            <span v-for="t in s.tools" :key="t" class="chip">{{ t }}</span>
          </div>
        </div>
      </div>

      <div class="arrow" aria-hidden="true"><span /></div>

      <div class="col">
        <h3>One bundle</h3>
        <p class="hint">Prefixed, curated, renamed</p>
        <div class="node bundle">
          <div class="title">
            <img :src="withBase('/logo-mark.svg')" alt="" />
            assistant
          </div>
          <ul class="tools">
            <li v-for="t in bundleTools" :key="t.name" :class="{ disabled: t.disabled }">
              <code>{{ t.name }}</code>
              <small v-if="t.from">was {{ t.from }}</small>
              <small v-else-if="t.disabled">disabled</small>
            </li>
          </ul>
        </div>
      </div>

      <div class="arrow" aria-hidden="true"><span /></div>

      <div class="col">
        <h3>Endpoints per client</h3>
        <p class="hint">Same tools, three contracts</p>
        <div v-for="e in endpoints" :key="e.path" class="node endpoint">
          <div class="title"><code>{{ e.path }}</code></div>
          <div class="meta"><strong>{{ e.client }}</strong> · {{ e.auth }}</div>
          <div class="note">{{ e.note }}</div>
        </div>
      </div>
    </div>
    <p class="caption">
      Every tool call passes the endpoint's auth, the bundle's curation, the client profile,
      the optional metering hook, and lands in the audit log. Sessions live in Valkey, so any
      replica serves any client.
    </p>
  </section>
</template>

<style scoped>
.pipeline {
  --bg: #242e30;
  --ink: #94cdd2;
  --muted: #8b8d8e;
  --line: rgba(148, 205, 210, 0.28);
  --red: #b02222;
  margin: 0 auto;
  padding: 0 24px 40px;
  max-width: 1152px;
}
@media (min-width: 640px) {
  .pipeline { padding: 0 48px 56px; }
}
@media (min-width: 960px) {
  .pipeline { padding: 0 64px 64px; }
}
.card {
  display: grid;
  grid-template-columns: 1fr;
  gap: 8px;
  padding: 24px;
  border-radius: 16px;
  background: var(--bg);
  color: var(--ink);
  font-size: 13px;
  line-height: 1.4;
}
@media (min-width: 960px) {
  .card {
    grid-template-columns: 1fr 40px 1.2fr 40px 1.3fr;
    gap: 0;
    padding: 28px 32px;
  }
}
h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: #fff;
}
.hint {
  margin: 2px 0 12px;
  color: var(--muted);
  font-size: 12px;
}
.node {
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 10px 12px;
  margin-bottom: 8px;
}
.title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  color: #fff;
}
.title img { height: 22px; width: auto; }
.chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
.chip {
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 1px 8px;
  font-family: var(--vp-font-family-mono);
  font-size: 11.5px;
  color: var(--ink);
}
.bundle { border-color: rgba(148, 205, 210, 0.6); }
.tools { list-style: none; margin: 8px 0 0; padding: 0; }
.tools li { display: flex; align-items: baseline; gap: 8px; padding: 2px 0; }
.tools code {
  font-family: var(--vp-font-family-mono);
  font-size: 12px;
  color: var(--ink);
  background: none;
  padding: 0;
}
.tools small { color: var(--muted); font-size: 11px; }
.tools .disabled code { color: var(--muted); text-decoration: line-through; }
.endpoint .title code {
  font-family: var(--vp-font-family-mono);
  font-size: 12.5px;
  color: #fff;
  background: none;
  padding: 0;
}
.meta { margin-top: 4px; color: var(--ink); }
.meta strong { color: #fff; font-weight: 600; }
.note { color: var(--muted); font-size: 12px; }
.arrow {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 4px 0;
}
.arrow span {
  display: block;
  width: 14px;
  height: 14px;
  border-right: 2px solid var(--ink);
  border-bottom: 2px solid var(--ink);
  transform: rotate(45deg);
}
@media (min-width: 960px) {
  .arrow span { transform: rotate(-45deg); }
}
.caption {
  margin: 16px auto 0;
  max-width: 720px;
  text-align: center;
  color: var(--vp-c-text-2);
  font-size: 14px;
  line-height: 1.6;
}
</style>
