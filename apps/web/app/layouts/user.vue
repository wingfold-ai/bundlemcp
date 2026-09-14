<script setup lang="ts">
// The layout for a signed-in person without admin rights: the catalogue and
// nothing else, so no management navigation is offered.
const { me } = useMe();

async function logout() {
  await fetch(`${apiBase()}/logout`, { method: "POST", credentials: "include" });
  gotoLogin("/");
}
</script>

<template>
  <div class="min-h-screen bg-muted text-default">
    <header class="border-b border-default bg-muted">
      <div class="mx-auto flex max-w-5xl items-center justify-between px-6 py-3">
        <NuxtLink to="/catalogue" data-testid="app-title" aria-label="bundlemcp">
          <img src="/lockup-light.svg" alt="bundlemcp" class="h-9 w-auto dark:hidden" />
          <img src="/lockup-dark.svg" alt="bundlemcp" class="h-9 w-auto hidden dark:block" />
        </NuxtLink>
        <div class="flex items-center gap-3 text-xs text-muted">
          <span data-testid="me-email">{{ me?.email }}</span>
          <button class="underline hover:text-primary" data-testid="logout" @click="logout">
            Sign out
          </button>
        </div>
      </div>
    </header>
    <main class="mx-auto max-w-5xl p-6">
      <slot />
    </main>
  </div>
</template>
