<script setup lang="ts">
import type { components } from "~~/types/api";

type AvailableEndpointRead = components["schemas"]["AvailableEndpointRead"];

// One bundle of the catalogue: its endpoints with the URL to paste into an
// MCP client and the steps for the client each endpoint is shaped for.
definePageMeta({ layout: false });

const api = useApi();
const route = useRoute();
const { me } = useMe();
const layout = computed(() => (me.value?.is_admin ? "default" : "user"));
const bundleName = computed(() => String(route.params.bundle));

const endpoints = ref<AvailableEndpointRead[]>([]);
const errorMsg = ref("");
const copied = ref("");

async function load() {
  const { data, error } = await api.GET("/api/v1/me/endpoints");
  if (error) {
    errorMsg.value = apiErrorMessage(error);
    return;
  }
  endpoints.value = (data ?? []).filter((ep) => ep.bundle_name === bundleName.value);
}
await load();

const description = computed(() => endpoints.value[0]?.bundle_description ?? null);

async function copyUrl(ep: AvailableEndpointRead) {
  await navigator.clipboard.writeText(ep.url);
  copied.value = ep.name;
  setTimeout(() => (copied.value = ""), 1500);
}

const CLIENT_LABEL: Record<string, string> = {
  default: "any MCP client",
  claude: "claude.ai",
  chatgpt: "ChatGPT",
};

function steps(ep: AvailableEndpointRead): string[] {
  switch (ep.profile) {
    case "claude":
      return [
        "In claude.ai open Settings → Connectors → Add custom connector.",
        "Enter a name and paste the URL; leave client id and secret empty.",
        "Click Connect: you sign in with your usual account and approve the consent screen.",
      ];
    case "chatgpt":
      return [
        "In ChatGPT open Settings → Connectors and create a custom connector.",
        "Paste the URL and choose OAuth; no client id or secret is needed.",
        "Sign in with your usual account and approve the consent screen.",
      ];
    default:
      return [
        "Add the URL as a remote MCP server in your client (claude.ai, ChatGPT, Claude Code, …).",
        "Choose OAuth when the client asks how to authenticate.",
        "Sign in with your usual account and approve the consent screen.",
      ];
  }
}
</script>

<template>
  <NuxtLayout :name="layout">
    <div class="space-y-6">
      <div>
        <NuxtLink to="/catalogue" class="text-xs text-muted underline">← All bundles</NuxtLink>
        <h1 class="text-lg font-semibold inline-flex items-center gap-2 mt-1">
          <UIcon name="i-lucide-package" class="size-5 text-muted" />{{ bundleName }}
        </h1>
        <p v-if="description" class="text-sm text-toned">{{ description }}</p>
      </div>

      <p v-if="errorMsg" class="text-red-600 text-sm" data-testid="error">{{ errorMsg }}</p>

      <div v-if="endpoints.length === 0" class="wf-card text-sm text-muted" data-testid="catalogue-empty">
        This bundle has no endpoint you can connect to.
      </div>

      <div class="grid gap-4 md:grid-cols-2" data-testid="catalogue-endpoints">
        <div
          v-for="ep in endpoints"
          :key="ep.name"
          class="wf-card space-y-3"
          :data-testid="`catalogue-${ep.name}`"
        >
          <div class="flex items-start justify-between gap-2">
            <h2 class="font-medium inline-flex items-center gap-1.5">
              <UIcon name="i-lucide-plug-zap" class="size-4 text-muted" />{{ ep.name }}
            </h2>
            <UBadge
              :icon="PROFILE_ICON[ep.profile]"
              :color="ep.profile === 'default' ? 'neutral' : 'primary'"
              variant="subtle"
              :title="PROFILE_HELP[ep.profile]"
            >
              {{ CLIENT_LABEL[ep.profile] }}
            </UBadge>
          </div>

          <div class="flex items-center gap-2">
            <code
              class="grow truncate rounded-md bg-elevated px-2 py-1 text-xs"
              :title="ep.url"
              :data-testid="`catalogue-url-${ep.name}`"
              >{{ ep.url }}</code
            >
            <UButton
              size="xs"
              variant="soft"
              :icon="copied === ep.name ? 'i-lucide-check' : 'i-lucide-copy'"
              @click="copyUrl(ep)"
            >
              {{ copied === ep.name ? "Copied" : "Copy" }}
            </UButton>
          </div>

          <ol class="list-decimal space-y-1 pl-5 text-xs text-toned">
            <li v-for="(step, i) in steps(ep)" :key="i">{{ step }}</li>
          </ol>
        </div>
      </div>
    </div>
  </NuxtLayout>
</template>
