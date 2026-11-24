---
title: Blog
description: "bundlemcp blog: Self-hostable MCP gateway that bundles all your MCP servers into one connector for any MCP
  client or AI tool, with one login and curated tools."
---

<script setup>
import { data as posts } from "./posts.data";
import { formatPostDate } from "../.vitepress/theme/post-date";
</script>

# Blog

**bundlemcp:** Self-hostable MCP gateway that bundles all your MCP servers into one connector for any MCP client or AI
tool, with one login and curated tools.

Posts on building and running it, newest first. Follow them with the [RSS feed](/blog/feed.xml).

<p v-if="posts.length === 0">There are no posts yet.</p>
<ul v-else class="blog-index">
  <li v-for="post in posts" :key="post.url">
    <time :datetime="post.date">{{ formatPostDate(post.date) }}</time>
    <a class="title" :href="post.url">{{ post.title }}</a>
    <span class="description">{{ post.description }}</span>
  </li>
</ul>
