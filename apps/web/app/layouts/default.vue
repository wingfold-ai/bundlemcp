<script setup lang="ts">
const { me } = useMe();
const route = useRoute();

const nav = [
  { to: "/servers", label: "Servers", testid: "nav-servers", icon: "i-lucide-server" },
  { to: "/bundles", label: "Bundles", testid: "nav-bundles", icon: "i-lucide-package" },
  // which bundle holds which server, as one grid across every bundle
  { to: "/bundles/matrix", label: "Composition", testid: "nav-matrix", icon: "i-lucide-grid-3x3", sub: true },
  // endpoints belong to bundles; the overview lists all of them across bundles
  { to: "/endpoints", label: "All endpoints", testid: "nav-endpoints", icon: "i-lucide-plug-zap", sub: true },
  { to: "/api-keys", label: "API keys", testid: "nav-api-keys", icon: "i-lucide-key-round" },
  { to: "/users", label: "Users", testid: "nav-users", icon: "i-lucide-users" },
  { to: "/audit", label: "Audit", testid: "nav-audit", icon: "i-lucide-scroll-text" },
  { to: "/logs", label: "Live logs", testid: "nav-logs", icon: "i-lucide-terminal" },
  { to: "/inspector", label: "Inspector", testid: "nav-inspector", icon: "i-lucide-search-code" },
  { to: "/settings", label: "Settings", testid: "nav-settings", icon: "i-lucide-settings" },
  // what a signed-in non-admin sees; useful to check before handing out a URL
  { to: "/catalogue", label: "Catalogue", testid: "nav-catalogue", icon: "i-lucide-layout-grid" },
];

/** A section stays highlighted on its detail pages too (/servers/SEO under Servers). */
function isActive(to: string): boolean {
  return route.path === to || route.path.startsWith(`${to}/`);
}

async function logout() {
  await fetch(`${apiBase()}/logout`, { method: "POST", credentials: "include" });
  gotoLogin("/");
}
</script>

<template>
  <div class="flex min-h-screen bg-muted text-default">
    <aside class="w-56 shrink-0 border-r border-default bg-muted p-4 flex flex-col gap-1">
      <NuxtLink to="/servers" class="mb-5 block" data-testid="app-title" aria-label="bundlemcp">
        <img src="/lockup-light.svg" alt="bundlemcp" class="h-9 w-auto dark:hidden" />
        <img src="/lockup-dark.svg" alt="bundlemcp" class="h-9 w-auto hidden dark:block" />
      </NuxtLink>
      <NuxtLink
        v-for="item in nav"
        :key="item.to"
        :to="item.to"
        :data-testid="item.testid"
        class="flex items-center gap-2 rounded-md px-2.5 py-1.5"
        :class="[
          item.sub ? 'ml-5 text-xs' : 'text-sm',
          isActive(item.to)
            ? 'bg-primary/10 text-primary font-medium hover:bg-primary/15'
            : [item.sub ? 'text-muted' : 'text-default', 'hover:bg-elevated'],
        ]"
      >
        <UIcon :name="item.icon" :class="item.sub ? 'size-3.5' : 'size-4'" class="shrink-0" />
        {{ item.label }}
      </NuxtLink>
      <div class="mt-auto pt-4 border-t border-default text-xs text-muted">
        <div data-testid="me-email">{{ me?.email }}</div>
        <button class="underline mt-1 hover:text-primary" data-testid="logout" @click="logout">
          Sign out
        </button>
      </div>
    </aside>
    <main class="grow min-w-0 p-6 max-w-5xl">
      <slot />
    </main>
  </div>
</template>
