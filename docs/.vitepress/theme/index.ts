import { h } from "vue";
import type { Theme } from "vitepress";
import DefaultTheme from "vitepress/theme";
import HomePipeline from "./HomePipeline.vue";
import ImageLightbox from "./ImageLightbox.vue";
import LikeC4Diagram from "./LikeC4Diagram.vue";
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
    app.component("LikeC4Diagram", LikeC4Diagram);
  },
} satisfies Theme;
