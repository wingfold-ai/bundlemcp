<script setup lang="ts">
import { onMounted, onUnmounted, ref } from "vue";

// Any image inside page content opens enlarged: scroll to zoom around the
// cursor, drag to pan, double-click to toggle 2×, Escape or a click on the
// backdrop to close.
const src = ref<string | null>(null);
const alt = ref("");
const scale = ref(1);
const tx = ref(0);
const ty = ref(0);

const MIN = 1;
const MAX = 8;
let dragging = false;
let moved = false;
let lastX = 0;
let lastY = 0;

function reset() {
  scale.value = 1;
  tx.value = 0;
  ty.value = 0;
}

function open(img: HTMLImageElement) {
  reset();
  src.value = img.currentSrc || img.src;
  alt.value = img.alt;
}

function close() {
  src.value = null;
}

function onDocumentClick(event: MouseEvent) {
  const target = event.target as HTMLElement | null;
  const img = target?.closest?.(".vp-doc img") as HTMLImageElement | null;
  if (!img || img.closest("a[href]") || img.closest(".likec4-embed")) return;
  event.preventDefault();
  open(img);
}

function onKey(event: KeyboardEvent) {
  if (!src.value) return;
  if (event.key === "Escape") close();
  if (event.key === "+" || event.key === "=") zoomBy(1.25);
  if (event.key === "-") zoomBy(0.8);
  if (event.key === "0") reset();
}

function zoomBy(factor: number, originX = 0, originY = 0) {
  const next = Math.min(MAX, Math.max(MIN, scale.value * factor));
  const ratio = next / scale.value;
  // keep the point under the cursor fixed while scaling
  tx.value = originX - (originX - tx.value) * ratio;
  ty.value = originY - (originY - ty.value) * ratio;
  scale.value = next;
  if (next === MIN) reset();
}

function onWheel(event: WheelEvent) {
  event.preventDefault();
  const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
  const originX = event.clientX - rect.left - rect.width / 2;
  const originY = event.clientY - rect.top - rect.height / 2;
  zoomBy(event.deltaY < 0 ? 1.15 : 1 / 1.15, originX, originY);
}

function onPointerDown(event: PointerEvent) {
  dragging = true;
  moved = false;
  lastX = event.clientX;
  lastY = event.clientY;
  (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
}

function onPointerMove(event: PointerEvent) {
  if (!dragging) return;
  const dx = event.clientX - lastX;
  const dy = event.clientY - lastY;
  if (Math.abs(dx) + Math.abs(dy) > 2) moved = true;
  tx.value += dx;
  ty.value += dy;
  lastX = event.clientX;
  lastY = event.clientY;
}

function onPointerUp() {
  dragging = false;
}

function onBackdropClick() {
  if (!moved) close();
  moved = false;
}

function onDoubleClick(event: MouseEvent) {
  const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
  const originX = event.clientX - rect.left - rect.width / 2;
  const originY = event.clientY - rect.top - rect.height / 2;
  if (scale.value > 1) reset();
  else zoomBy(2, originX, originY);
}

onMounted(() => {
  document.addEventListener("click", onDocumentClick);
  document.addEventListener("keydown", onKey);
});
onUnmounted(() => {
  document.removeEventListener("click", onDocumentClick);
  document.removeEventListener("keydown", onKey);
});
</script>

<template>
  <Teleport to="body">
    <div
      v-if="src"
      class="lightbox"
      role="dialog"
      aria-modal="true"
      :aria-label="alt || 'Enlarged image'"
      @click="onBackdropClick"
      @wheel="onWheel"
    >
      <button class="lightbox-close" type="button" aria-label="Close" @click.stop="close">×</button>
      <div class="lightbox-toolbar" @click.stop>
        <button type="button" aria-label="Zoom out" @click="zoomBy(0.8)">−</button>
        <span>{{ Math.round(scale * 100) }}%</span>
        <button type="button" aria-label="Zoom in" @click="zoomBy(1.25)">+</button>
        <button type="button" aria-label="Reset zoom" @click="reset">fit</button>
      </div>
      <div
        class="lightbox-stage"
        :class="{ zoomed: scale > 1 }"
        @pointerdown="onPointerDown"
        @pointermove="onPointerMove"
        @pointerup="onPointerUp"
        @pointercancel="onPointerUp"
        @dblclick="onDoubleClick"
        @click.stop="onBackdropClick"
      >
        <img
          class="lightbox-img"
          :src="src"
          :alt="alt"
          draggable="false"
          :style="{ transform: `translate(${tx}px, ${ty}px) scale(${scale})` }"
          @click.stop
        />
      </div>
      <p v-if="alt" class="lightbox-caption">{{ alt }}</p>
    </div>
  </Teleport>
</template>

<style scoped>
.lightbox {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 24px;
  background: rgba(0, 0, 0, 0.9);
  cursor: zoom-out;
  overscroll-behavior: contain;
}
.lightbox-stage {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 86vh;
  overflow: hidden;
  cursor: grab;
  touch-action: none;
}
.lightbox-stage.zoomed {
  cursor: grabbing;
}
.lightbox-img {
  max-width: min(96vw, 1800px);
  max-height: 86vh;
  width: auto;
  height: auto;
  border-radius: 8px;
  box-shadow: 0 12px 48px rgba(0, 0, 0, 0.5);
  transform-origin: center center;
  transition: transform 0.05s linear;
  user-select: none;
  cursor: inherit;
}
.lightbox-caption {
  margin: 0;
  max-width: 80ch;
  text-align: center;
  color: #ddd;
  font-size: 14px;
  line-height: 1.5;
}
.lightbox-close {
  position: absolute;
  top: 16px;
  right: 20px;
  width: 40px;
  height: 40px;
  border: 0;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.12);
  color: #fff;
  font-size: 26px;
  line-height: 1;
  cursor: pointer;
}
.lightbox-close:hover {
  background: rgba(255, 255, 255, 0.24);
}
.lightbox-toolbar {
  position: absolute;
  top: 20px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.12);
  color: #fff;
  font-size: 13px;
  cursor: default;
}
.lightbox-toolbar button {
  min-width: 30px;
  height: 30px;
  border: 0;
  border-radius: 999px;
  background: transparent;
  color: #fff;
  font-size: 16px;
  cursor: pointer;
}
.lightbox-toolbar button:hover {
  background: rgba(255, 255, 255, 0.18);
}
.lightbox-toolbar span {
  min-width: 44px;
  text-align: center;
  font-variant-numeric: tabular-nums;
}
</style>

<style>
/* unscoped: the theme class sits on <html>, outside this component, and a
   scoped rule would outrank the dark override */
.lightbox-img {
  background: #ffffff;
}
.dark .lightbox-img {
  background: #1b1b1f;
}
</style>
