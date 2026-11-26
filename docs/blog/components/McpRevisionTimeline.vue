<script setup lang="ts">
// Timeline for the MCP sessions post. Its one statement: the protocol dropped
// sessions in July 2026, the clients had not followed by autumn, so a server
// has to offer both revisions in the gap. Two bars on one time axis, protocol
// above clients, with the gap shaded across both. Below 640px it becomes a list.

const start = Date.parse("2026-01-01");
const end = Date.parse("2026-12-31");
const at = (date: string) => ((Date.parse(date) - start) / (end - start)) * 100;

const removed = at("2026-07-28");
const lastEvidence = at("2026-09-21");
const today = at("2026-11-26");

const notes = [
  { left: at("2026-07-31"), date: "31 Jul 2026", text: "Claude's apps and VS Code still session-based" },
  { left: at("2026-09-21"), date: "21 Sep 2026", text: "Cursor: “no timeline” for the new revision" },
];
</script>

<template>
  <figure class="revision-timeline">
    <p class="headline">
      The protocol dropped sessions in July 2026. The clients had not followed by autumn.
    </p>

    <div class="chart" aria-hidden="true">
      <div class="gap" :style="{ left: removed + '%', width: today - removed + '%' }">
        <span>servers must offer both</span>
      </div>

      <div class="row">
        <span class="row-name">Protocol</span>
        <div class="bar">
          <div class="segment session" :style="{ left: 0, width: removed + '%' }">
            sessions <small>since 2025-03-26</small>
          </div>
          <div class="segment stateless" :style="{ left: removed + '%', right: 0 }">no sessions</div>
        </div>
      </div>

      <div class="row">
        <span class="row-name">Clients</span>
        <div class="bar">
          <div class="segment session" :style="{ left: 0, width: lastEvidence + '%' }">sessions</div>
          <div
            class="segment unknown"
            :style="{ left: lastEvidence + '%', width: today - lastEvidence + '%' }"
            title="No newer public statement"
          >no data</div>
          <span v-for="n in notes" :key="n.date" class="dot" :style="{ left: n.left + '%' }" />
        </div>
      </div>

      <div class="notes">
        <div
          v-for="(n, i) in notes"
          :key="n.date"
          class="note"
          :class="'row-' + i"
          :style="{ left: n.left + '%' }"
        >
          <strong>{{ n.date }}</strong>{{ n.text }}
        </div>
      </div>

      <div class="axis">
        <span class="tick first" style="left: 0">Jan 2026</span>
        <span class="tick strong" :style="{ left: removed + '%' }">28 Jul</span>
        <span class="tick" :style="{ left: today + '%' }">today</span>
      </div>
    </div>

    <ul class="list">
      <li><strong>2025-03-26 to 2025-11-25</strong> Three revisions, all with sessions</li>
      <li class="stateless"><strong>2026-07-28</strong> The protocol drops sessions</li>
      <li v-for="n in notes" :key="n.date"><strong>{{ n.date }}</strong> {{ n.text }}</li>
      <li><strong>Until the clients move</strong> Servers must offer both revisions</li>
    </ul>
  </figure>
</template>

<style scoped>
.revision-timeline {
  margin: 24px 0 32px;
  padding: 20px 20px 16px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 12px;
  background: var(--vp-c-bg-soft);
}
.headline {
  margin: 0 0 20px;
  font-weight: 600;
  color: var(--vp-c-text-1);
}
.chart {
  position: relative;
  margin-left: 72px;
  padding-top: 26px;
}
/* the gap, shaded behind both bars */
.gap {
  position: absolute;
  top: 0;
  bottom: 104px;
  border-left: 2px solid var(--vp-c-brand-1);
  background: repeating-linear-gradient(-45deg, var(--vp-c-brand-soft) 0 6px, transparent 6px 12px);
  border-radius: 0 6px 6px 0;
}
.gap span {
  position: absolute;
  top: 3px;
  left: 6px;
  font-size: 12px;
  font-weight: 600;
  color: var(--vp-c-brand-1);
  white-space: nowrap;
}
.row {
  position: relative;
  height: 30px;
  margin-bottom: 14px;
}
.row-name {
  position: absolute;
  left: -72px;
  top: 6px;
  font-size: 13px;
  font-weight: 600;
  color: var(--vp-c-text-2);
}
.bar {
  position: relative;
  height: 100%;
}
.segment {
  position: absolute;
  top: 0;
  bottom: 0;
  padding: 0 10px;
  border-radius: 6px;
  font-size: 12.5px;
  font-weight: 600;
  line-height: 30px;
  white-space: nowrap;
  overflow: hidden;
}
.segment small {
  font-weight: 400;
  opacity: 0.8;
}
.segment.session {
  background: var(--vp-c-default-soft);
  color: var(--vp-c-text-2);
}
.segment.stateless {
  background: var(--vp-c-brand-3);
  color: var(--vp-c-white);
}
.segment.unknown {
  color: var(--vp-c-text-3);
  font-weight: 400;
  background: repeating-linear-gradient(90deg, var(--vp-c-default-soft) 0 8px, transparent 8px 14px);
}
.dot {
  position: absolute;
  top: 50%;
  width: 10px;
  height: 10px;
  margin: -5px 0 0 -5px;
  border-radius: 50%;
  background: var(--vp-c-text-1);
  border: 2px solid var(--vp-c-bg-soft);
}
.notes {
  position: relative;
  height: 84px;
}
.note {
  position: absolute;
  width: 230px;
  transform: translateX(-100%);
  padding-right: 10px;
  text-align: right;
  font-size: 12.5px;
  line-height: 1.35;
  color: var(--vp-c-text-2);
}
.note strong {
  display: block;
  color: var(--vp-c-text-1);
}
.note.row-0 {
  top: -6px;
}
.note.row-1 {
  top: 34px;
}
.axis {
  position: relative;
  height: 20px;
  border-top: 1px solid var(--vp-c-divider);
}
.tick {
  position: absolute;
  top: 4px;
  font-size: 12px;
  color: var(--vp-c-text-3);
  white-space: nowrap;
  transform: translateX(-50%);
}
.tick.first {
  transform: none;
}
.tick.strong {
  color: var(--vp-c-brand-1);
  font-weight: 600;
}
.list {
  display: none;
}
@media (max-width: 640px) {
  .chart {
    display: none;
  }
  .list {
    display: block;
    margin: 0;
    padding: 0;
    list-style: none;
  }
  .list li {
    margin: 0;
    padding: 6px 0;
    font-size: 14px;
    color: var(--vp-c-text-2);
    border-top: 1px solid var(--vp-c-divider);
  }
  .list li strong {
    display: block;
    color: var(--vp-c-text-1);
  }
  .list li.stateless strong {
    color: var(--vp-c-brand-1);
  }
}
</style>
