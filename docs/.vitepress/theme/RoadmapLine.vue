<script setup lang="ts">
import { computed } from "vue";
import { withBase } from "vitepress";
import changes from "virtual:roadmap-changes";
import type { RoadmapStation } from "../roadmap-stations";

// The roadmap as a metro line: one stop per station, its themes in cards below it.
// Wide screens run the line left to right, narrow ones top to bottom. The station
// marked `changes` lists the active OpenSpec changes instead of themes of its own.
const props = defineProps<{ stations: RoadmapStation[] }>();

const stops = computed(() =>
  props.stations.map((station, i) => ({
    ...station,
    // the segment into Later is dashed: it is a direction, not a plan
    dashedAfter: props.stations[i + 1]?.state === "later",
    last: i === props.stations.length - 1,
  })),
);

// Internal links go through the site base; absolute URLs are left alone.
function href(link: string): string {
  return /^https?:\/\//.test(link) ? link : withBase(link);
}

function percent(done: number, total: number): number {
  return total ? Math.round((done / total) * 100) : 0;
}
</script>

<template>
  <ol class="roadmap">
    <li
      v-for="stop in stops"
      :key="stop.title"
      class="station"
      :class="[stop.state, { 'dashed-after': stop.dashedAfter, last: stop.last }]"
    >
      <div class="stop">
        <span class="dot" aria-hidden="true" />
        <span class="track" aria-hidden="true" />
      </div>
      <div class="label">
        <h3>{{ stop.title }}</h3>
        <p v-if="stop.tag" class="tag">{{ stop.tag }}</p>
        <p v-if="stop.subtitle" class="subtitle">{{ stop.subtitle }}</p>
      </div>

      <ul v-if="stop.changes" class="cards">
        <li v-for="change in changes" :key="change.name" class="card change">
          <a v-if="change.url" class="name" :href="change.url">{{ change.name }}</a>
          <span v-else class="name">{{ change.name }}</span>
          <p v-if="change.why" class="note clamp" :title="change.why">{{ change.why }}</p>
          <div v-if="change.total" class="progress" :title="`${change.done} of ${change.total} tasks done`">
            <span class="bar"><span :style="{ width: `${percent(change.done, change.total)}%` }" /></span>
            <span class="count">{{ change.done }}/{{ change.total }}</span>
          </div>
        </li>
        <li v-if="!changes.length" class="card empty">
          Nothing in flight right now; see Next.
        </li>
      </ul>

      <ul v-else class="cards">
        <li v-for="theme in stop.themes" :key="theme.title" class="card">
          <a v-if="theme.link" class="title" :href="href(theme.link)">{{ theme.title }}</a>
          <span v-else class="title">{{ theme.title }}</span>
          <p v-if="theme.note" class="note">{{ theme.note }}</p>
        </li>
      </ul>
    </li>
  </ol>
</template>

<style scoped>
.roadmap {
  --dot: 18px;
  --rail: 4px;
  --accent: var(--vp-c-brand-1);
  --muted: var(--vp-c-text-3);
  list-style: none;
  margin: 24px 0 32px;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 0 16px;
}
.vp-doc .roadmap li + li {
  margin-top: 0;
}
/* wide screens: five columns need more than the prose column, so the line breaks
   out of it, centred on the page; the text around it keeps its reading width */
@media (min-width: 1200px) {
  .roadmap {
    width: min(1120px, calc(100vw - 96px));
    position: relative;
    left: 50%;
    transform: translateX(-50%);
  }
}
.station {
  position: relative;
  min-width: 0;
}

/* the stop: a dot, and the rail that runs on to the next stop */
.stop {
  position: relative;
  height: var(--dot);
  margin-bottom: 12px;
}
.dot {
  position: absolute;
  left: 0;
  top: 0;
  width: var(--dot);
  height: var(--dot);
  border-radius: 50%;
  border: var(--rail) solid var(--accent);
  background: var(--vp-c-bg);
  z-index: 1;
  box-sizing: border-box;
}
.reached .dot,
.current .dot {
  background: var(--accent);
}
.current .dot {
  box-shadow: 0 0 0 6px var(--vp-c-brand-soft);
}
.later .dot {
  border-color: var(--muted);
  border-style: dashed;
}
.track {
  position: absolute;
  top: calc((var(--dot) - var(--rail)) / 2);
  left: var(--dot);
  /* across this column and the gap, to the next dot */
  right: -16px;
  height: var(--rail);
  background: var(--accent);
}
.planned .track {
  background: var(--vp-c-brand-soft);
  border-top: var(--rail) solid var(--accent);
  height: 0;
  opacity: 0.55;
}
.dashed-after .track {
  background: none;
  height: 0;
  border-top: var(--rail) dashed var(--muted);
  opacity: 1;
}
.last .track {
  display: none;
}

.label h3 {
  margin: 0;
  padding: 0;
  border: 0;
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--vp-c-text-1);
}
.label .tag {
  margin: 2px 0 0;
  font-family: var(--vp-font-family-mono);
  font-size: 12px;
  line-height: 1.4;
  color: var(--accent);
}
.later .label .tag {
  color: var(--muted);
}
.label .subtitle {
  margin: 2px 0 0;
  font-size: 14px;
  font-weight: 600;
  line-height: 1.35;
  color: var(--vp-c-text-1);
}

.cards {
  list-style: none;
  margin: 12px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.vp-doc .cards li + li {
  margin-top: 0;
}
.card {
  margin: 0;
  padding: 8px 10px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 10px;
  background: var(--vp-c-bg-soft);
  font-size: 13px;
  line-height: 1.4;
  overflow-wrap: anywhere;
}
.reached .card {
  border-color: color-mix(in srgb, var(--accent) 35%, var(--vp-c-divider));
}
.later .card {
  border-style: dashed;
  background: transparent;
}
.card .title {
  font-weight: 600;
  color: var(--vp-c-text-1);
}
.vp-doc .card a.title,
.vp-doc .card a.name {
  color: var(--accent);
  text-decoration: none;
}
.vp-doc .card a.title:hover,
.vp-doc .card a.name:hover {
  text-decoration: underline;
}
.card .note {
  margin: 4px 0 0;
  font-size: 12px;
  line-height: 1.45;
  color: var(--vp-c-text-2);
}
.card .clamp {
  display: -webkit-box;
  -webkit-line-clamp: 4;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.change .name {
  font-family: var(--vp-font-family-mono);
  font-size: 12px;
  font-weight: 600;
}
.progress {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 6px;
}
.progress .bar {
  flex: 1;
  height: 6px;
  border-radius: 3px;
  background: var(--vp-c-divider);
  overflow: hidden;
}
.progress .bar span {
  display: block;
  height: 100%;
  background: var(--accent);
}
.progress .count {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  color: var(--vp-c-text-2);
}
.empty {
  color: var(--vp-c-text-2);
  font-style: italic;
  border-style: dashed;
  background: transparent;
}

/* narrow screens: the line runs down the left edge, cards beside it */
@media (max-width: 1199px) {
  .roadmap {
    grid-template-columns: minmax(0, 1fr);
  }
  .station {
    padding: 0 0 24px 34px;
  }
  .stop {
    position: absolute;
    left: 0;
    top: 0;
    bottom: 0;
    width: var(--dot);
    height: auto;
    margin: 0;
  }
  .track,
  .planned .track,
  .dashed-after .track {
    top: var(--dot);
    bottom: 0;
    left: calc((var(--dot) - var(--rail)) / 2);
    right: auto;
    width: var(--rail);
    height: auto;
    border-top: 0;
  }
  .planned .track {
    background: var(--accent);
  }
  .dashed-after .track {
    width: 0;
    background: none;
    border-left: var(--rail) dashed var(--muted);
  }
  .cards {
    margin-top: 8px;
  }
}
</style>
