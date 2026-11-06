<script setup lang="ts">
/**
 * Says that the source and the container images are not public yet, on pages whose
 * steps need them. Renders nothing once the site is built with the repository public.
 */
import { useData } from "vitepress";

const { theme } = useData();
</script>

<template>
  <div v-if="!theme.repositoryPublic" class="custom-block info" data-testid="repository-notice">
    <p class="custom-block-title">Not public yet</p>
    <p>
      bundlemcp's source code and container images are being prepared for public release. The
      commands on this page need them, so they work once the repository is public.
    </p>
  </div>
</template>
