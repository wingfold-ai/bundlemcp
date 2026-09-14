<script setup lang="ts">
import { onMounted, onUnmounted, ref } from "vue";
import { withBase } from "vitepress";

// Renders one view of the LikeC4 model as the interactive web component that
// `likec4 codegen webcomponent` writes to public/likec4-views.js during the
// docs build: pan, zoom, click-through to related views, fullscreen browsing.
const props = defineProps<{ view: string }>();
const ready = ref(false);
const host = ref<HTMLElement | null>(null);
// Follow the theme through the <html> class the appearance toggle writes,
// which is what the rest of the page is styled from.
const dark = ref(false);
let observer: MutationObserver | undefined;

let loading: Promise<void> | undefined;
function loadOnce(): Promise<void> {
  if (customElements.get("likec4-view")) return Promise.resolve();
  if (!loading) {
    loading = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = withBase("/likec4-views.js");
      script.async = true;
      script.onload = () => resolve();
      script.onerror = () => reject(new Error("likec4-views.js failed to load"));
      document.head.appendChild(script);
    });
  }
  return loading;
}

// The component draws relationship labels at 14px regardless of the view's
// text size; at documentation width that is too small next to xl node text.
// The rules live in the element's shadow root, so they are adopted there.
const LABEL_CSS = `
  /* one line, not wrapped into the box the layout sized for 14px text; the
     shift keeps the wider label centred on its original position */
  .likec4-edge-label {
    max-width: none !important;
    white-space: nowrap;
    transform: translateX(-15%);
  }
  .likec4-edge-label__text {
    font-size: 21px;
    line-height: 1.25;
    white-space: nowrap !important;
    overflow-wrap: normal !important;
  }
  .likec4-edge-label .likec4-edge-label__technology {
    font-size: 18px !important;
    line-height: 1.2 !important;
    opacity: 0.9;
    white-space: nowrap !important;
  }
  /* zone titles such as "Replicas ×N" */
  .likec4-compound-title {
    font-size: 22px;
    letter-spacing: 0.5px;
    white-space: nowrap;
  }
`;
let labelSheet: CSSStyleSheet | undefined;

function adopt(root: ShadowRoot): void {
  if (!labelSheet) {
    labelSheet = new CSSStyleSheet();
    labelSheet.replaceSync(LABEL_CSS);
  }
  if (!root.adoptedStyleSheets.includes(labelSheet)) {
    root.adoptedStyleSheets = [...root.adoptedStyleSheets, labelSheet];
  }
}

// The diagram renders inside a shadow root nested in the element's own, and
// the fullscreen browser reuses it, so every root below the element gets the
// sheet; the observer re-applies it when the component re-renders.
function enlargeLabels(node: Element): void {
  const root = node.shadowRoot;
  if (!root) return;
  adopt(root);
  root.querySelectorAll("*").forEach((child) => enlargeLabels(child));
}

let labelObserver: MutationObserver | undefined;
function watchLabels(el: HTMLElement): void {
  enlargeLabels(el);
  const root = el.shadowRoot;
  if (!root) return;
  labelObserver = new MutationObserver(() => enlargeLabels(el));
  labelObserver.observe(root, { childList: true, subtree: true });
}

onMounted(async () => {
  const root = document.documentElement;
  dark.value = root.classList.contains("dark");
  observer = new MutationObserver(() => {
    dark.value = root.classList.contains("dark");
  });
  observer.observe(root, { attributes: true, attributeFilter: ["class"] });
  await loadOnce();
  ready.value = true;
  // the shadow root exists once the element has upgraded and connected
  await new Promise((resolve) => requestAnimationFrame(resolve));
  const el = host.value?.querySelector("likec4-view") as HTMLElement | null;
  if (el) watchLabels(el);
});
onUnmounted(() => {
  observer?.disconnect();
  labelObserver?.disconnect();
});
</script>

<template>
  <div ref="host" class="likec4-embed">
    <likec4-view
      v-if="ready"
      :view-id="props.view"
      browser="true"
      :color-scheme="dark ? 'dark' : 'light'"
    />
    <div v-else class="placeholder">Loading diagram…</div>
    <p class="hint">Drag to pan. Click an element to open the fullscreen browser, where you can zoom and navigate between views.</p>
  </div>
</template>

<style scoped>
.likec4-embed {
  margin: 8px 0 24px;
}
.likec4-embed likec4-view {
  display: block;
  width: 100%;
  border: 1px solid var(--vp-c-divider);
  border-radius: 12px;
  overflow: hidden;
  background: var(--vp-c-bg-soft);
}
.placeholder {
  min-height: 320px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--vp-c-text-3);
  border: 1px dashed var(--vp-c-divider);
  border-radius: 12px;
}
.hint {
  margin: 6px 0 0;
  text-align: center;
  font-size: 12px;
  color: var(--vp-c-text-3);
}
</style>
