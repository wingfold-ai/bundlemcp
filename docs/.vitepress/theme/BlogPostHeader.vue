<script setup lang="ts">
// Above every blog post: the way back to the index, the title, the date and the
// author line. Posts carry no heading of their own; the title is the frontmatter's.
import { computed } from "vue";
import { useData } from "vitepress";
import { formatPostDate } from "./post-date";

const { frontmatter, page } = useData();
const isPost = computed(() => {
  const path = page.value.relativePath;
  return /^blog\/[^/]+\.md$/.test(path) && path !== "blog/index.md";
});
</script>

<template>
  <header v-if="isPost" class="vp-doc blog-post-header">
    <a class="back" href="/blog/">← All posts</a>
    <h1>{{ frontmatter.title }}</h1>
    <p class="meta">
      <span v-if="frontmatter.draft" class="draft">Draft</span>
      <time v-if="frontmatter.date" :datetime="frontmatter.date">{{
        formatPostDate(frontmatter.date)
      }}</time>
      <template v-if="frontmatter.author">
        <span aria-hidden="true"> · </span>
        <a v-if="frontmatter.authorLink" :href="frontmatter.authorLink" rel="author" target="_blank">{{
          frontmatter.author
        }}</a>
        <span v-else>{{ frontmatter.author }}</span>
      </template>
    </p>
  </header>
</template>

<style scoped>
.blog-post-header {
  margin-bottom: 32px;
}
.blog-post-header h1 {
  margin-top: 8px;
}
.back {
  font-size: 14px;
  font-weight: 500;
  text-decoration: none;
}
.meta {
  margin: 12px 0 0;
  color: var(--vp-c-text-2);
  font-size: 15px;
}
.draft {
  margin-right: 8px;
  padding: 2px 8px;
  border-radius: 4px;
  background: var(--vp-c-warning-soft);
  color: var(--vp-c-warning-1);
  font-size: 13px;
  font-weight: 600;
}
</style>
