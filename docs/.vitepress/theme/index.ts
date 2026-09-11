import { h } from "vue";
import type { Theme } from "vitepress";
import DefaultTheme from "vitepress/theme";
import HomePipeline from "./HomePipeline.vue";
import ImageLightbox from "./ImageLightbox.vue";
import "./custom.css";

export default {
  extends: DefaultTheme,
  Layout: () =>
    h(DefaultTheme.Layout, null, {
      "home-hero-after": () => h(HomePipeline),
      "layout-bottom": () => h(ImageLightbox),
    }),
  enhanceApp({ app }) {
    // usable inside Markdown pages as <HomePipeline compact />
    app.component("HomePipeline", HomePipeline);
  },
} satisfies Theme;
