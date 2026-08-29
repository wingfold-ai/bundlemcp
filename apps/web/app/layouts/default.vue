<script setup lang="ts">
const { me } = useMe();

const nav = [
  { to: "/servers", label: "Servers", testid: "nav-servers" },
  { to: "/bundles", label: "Bundles", testid: "nav-bundles" },
  { to: "/endpoints", label: "Endpoints", testid: "nav-endpoints" },
  { to: "/api-keys", label: "API keys", testid: "nav-api-keys" },
  { to: "/users", label: "Users", testid: "nav-users" },
  { to: "/audit", label: "Audit", testid: "nav-audit" },
  { to: "/logs", label: "Live logs", testid: "nav-logs" },
  { to: "/inspector", label: "Inspector", testid: "nav-inspector" },
  { to: "/settings", label: "Settings", testid: "nav-settings" },
];

async function logout() {
  await fetch(`${apiBase()}/logout`, { method: "POST", credentials: "include" });
  gotoLogin("/");
}
</script>

<template>
  <div class="flex min-h-screen">
    <aside class="w-52 shrink-0 border-r border-gray-300 p-4 flex flex-col gap-1">
      <div class="font-semibold mb-4" data-testid="app-title">bundlemcp</div>
      <NuxtLink
        v-for="item in nav"
        :key="item.to"
        :to="item.to"
        :data-testid="item.testid"
        class="rounded px-2 py-1 text-sm hover:bg-gray-100 dark:hover:bg-gray-800"
        active-class="bg-gray-200 dark:bg-gray-700 font-medium"
      >
        {{ item.label }}
      </NuxtLink>
      <div class="mt-auto pt-4 border-t border-gray-200 text-xs text-gray-500">
        <div data-testid="me-email">{{ me?.email }}</div>
        <button class="underline mt-1" data-testid="logout" @click="logout">
          Sign out
        </button>
      </div>
    </aside>
    <main class="grow p-6 max-w-5xl">
      <slot />
    </main>
  </div>
</template>
