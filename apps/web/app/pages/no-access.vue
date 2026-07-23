<script setup lang="ts">
definePageMeta({ layout: false });
const { me } = useMe();
</script>

<template>
  <div class="min-h-screen flex items-center justify-center">
    <div class="wf-card max-w-md text-center" data-testid="no-access">
      <h1 class="text-lg font-semibold mb-2">No access</h1>
      <p class="text-sm text-gray-500">
        {{ me?.email }} is signed in but is not an administrator of this
        gateway. Ask an admin to add you, then sign in again.
      </p>
    </div>
  </div>
</template>
