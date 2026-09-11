<script setup lang="ts">
import { onMounted, onUnmounted, ref } from "vue";

// Any image inside page content opens enlarged; diagrams are exported at
// twice their layout size, so the enlarged view is where labels become
// readable.
const src = ref<string | null>(null);
const alt = ref("");

function onClick(event: MouseEvent) {
  const target = event.target as HTMLElement | null;
  const img = target?.closest?.(".vp-doc img, .pipeline img.zoomable") as HTMLImageElement | null;
  if (!img || img.closest("a[href]")) return;
  event.preventDefault();
  src.value = img.currentSrc || img.src;
  alt.value = img.alt;
}

function close() {
  src.value = null;
}

function onKey(event: KeyboardEvent) {
  if (event.key === "Escape") close();
}

onMounted(() => {
  document.addEventListener("click", onClick);
  document.addEventListener("keydown", onKey);
});
onUnmounted(() => {
  document.removeEventListener("click", onClick);
  document.removeEventListener("keydown", onKey);
});
</script>

<template>
  <Teleport to="body">
      <div v-if="src" class="lightbox" role="dialog" aria-modal="true" :aria-label="alt || 'Enlarged image'" @click="close">
        <button class="lightbox-close" type="button" aria-label="Close" @click.stop="close">×</button>
        <img class="lightbox-img" :src="src" :alt="alt" @click.stop />
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
}
.lightbox img {
  max-width: min(96vw, 1800px);
  max-height: 86vh;
  width: auto;
  height: auto;
  border-radius: 8px;
  box-shadow: 0 12px 48px rgba(0, 0, 0, 0.5);
  cursor: default;
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
