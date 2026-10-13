<script setup lang="ts">
import type { components } from "~~/types/api";

type AvailableEndpointRead = components["schemas"]["AvailableEndpointRead"];
type CatalogueToolRead = components["schemas"]["CatalogueToolRead"];
type CataloguePromptRead = components["schemas"]["CataloguePromptRead"];
type CatalogueResourceRead = components["schemas"]["CatalogueResourceRead"];

// One bundle of the catalogue: its endpoints with the URL to paste into an
// MCP client and the steps for the client each endpoint is shaped for.
definePageMeta({ layout: false });

const api = useApi();
const route = useRoute();
const { me } = useMe();
const layout = computed(() => (me.value?.is_admin ? "default" : "user"));
const bundleName = computed(() => String(route.params.bundle));

const endpoints = ref<AvailableEndpointRead[]>([]);
const tools = ref<CatalogueToolRead[]>([]);
const prompts = ref<CataloguePromptRead[]>([]);
const resources = ref<CatalogueResourceRead[]>([]);
const errorMsg = ref("");
const copied = ref("");

async function load() {
  // Both requests are started before either is awaited, so they overlap.
  const endpointRequest = api.GET("/api/v1/me/endpoints");
  const bundlePath = { params: { path: { bundle_name: bundleName.value } } };
  const toolRequest = api.GET("/api/v1/me/bundles/{bundle_name}/tools", bundlePath);
  // BND-36: the context the bundle itself offers
  const promptRequest = api.GET("/api/v1/me/bundles/{bundle_name}/prompts", bundlePath);
  const resourceRequest = api.GET("/api/v1/me/bundles/{bundle_name}/resources", bundlePath);
  const { data: endpointData, error: endpointError } = await endpointRequest;
  // A bundle with no endpoint this person can use answers 404 here; the empty
  // endpoint list already says so, so the tool list simply stays empty.
  const { data: toolData } = await toolRequest;
  const { data: promptData } = await promptRequest;
  const { data: resourceData } = await resourceRequest;
  if (endpointError) {
    errorMsg.value = apiErrorMessage(endpointError);
    return;
  }
  endpoints.value = (endpointData ?? []).filter((ep) => ep.bundle_name === bundleName.value);
  tools.value = toolData ?? [];
  prompts.value = promptData ?? [];
  resources.value = resourceData ?? [];
}
await load();

const description = computed(() => endpoints.value[0]?.bundle_description ?? null);
const overview = computed(() => endpoints.value[0]?.bundle_overview ?? null);
/** Paragraphs of the overview, split on blank lines so the text keeps its shape. */
const overviewParagraphs = computed(() =>
  (overview.value ?? "").split(/\n\s*\n/).map((p) => p.trim()).filter(Boolean),
);
/** Tools grouped by the server that provides them, in the order the API returned. */
const toolsByServer = computed(() => {
  const grouped = new Map<string, CatalogueToolRead[]>();
  for (const tool of tools.value) {
    const existing = grouped.get(tool.server_name);
    if (existing) existing.push(tool);
    else grouped.set(tool.server_name, [tool]);
  }
  return [...grouped.entries()];
});

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
        <!-- The heading is a block, so the link above it keeps its own line;
             an inline-flex heading would sit beside the link. -->
        <NuxtLink
          to="/catalogue"
          class="inline-flex items-center gap-1.5 text-sm text-muted hover:text-default mb-2"
          data-testid="back-to-catalogue"
        >
          <UIcon name="i-lucide-arrow-left" class="size-4" />All bundles
        </NuxtLink>
        <h1 class="text-lg font-semibold flex items-center gap-2">
          <UIcon name="i-lucide-package" class="size-5 text-muted" />{{ bundleName }}
        </h1>
        <p v-if="description" class="text-sm text-toned">{{ description }}</p>
      </div>

      <p v-if="errorMsg" class="text-red-600 text-sm" data-testid="error">{{ errorMsg }}</p>

      <div v-if="overviewParagraphs.length" class="wf-card space-y-2" data-testid="catalogue-overview">
        <h2 class="text-sm font-semibold">About this bundle</h2>
        <p v-for="(paragraph, i) in overviewParagraphs" :key="i" class="text-sm text-toned">
          {{ paragraph }}
        </p>
      </div>

      <div v-if="tools.length" class="space-y-3" data-testid="catalogue-tools">
        <div>
          <h2 class="text-sm font-semibold">
            Tools <span class="text-muted font-normal">({{ tools.length }})</span>
          </h2>
          <p class="text-xs text-muted">
            What a client connected to this bundle can call, and what each tool does.
          </p>
        </div>
        <div v-for="[server, serverTools] in toolsByServer" :key="server" class="wf-card space-y-2">
          <h3 class="inline-flex items-center gap-1.5 text-sm font-medium">
            <UIcon name="i-lucide-server" class="size-4 text-muted" />{{ server }}
          </h3>
          <ul class="divide-y divide-default">
            <li
              v-for="tool in serverTools"
              :key="tool.name"
              class="py-2 first:pt-0 last:pb-0"
              :data-testid="`catalogue-tool-${tool.name}`"
            >
              <!-- The title is what this reader needs; the prefixed wire name is
                   how the model addresses the tool, so it stays on hover unless
                   the server published no title and it is all we have. -->
              <p v-if="tool.title" class="text-sm" :title="tool.name">{{ tool.title }}</p>
              <code v-else class="rounded bg-elevated px-1.5 py-0.5 text-xs">{{ tool.name }}</code>
              <p v-if="tool.description" class="mt-1 text-xs text-toned">{{ tool.description }}</p>
              <p v-else class="mt-1 text-xs text-muted italic">No description published.</p>
            </li>
          </ul>
        </div>
      </div>

      <div
        v-if="prompts.length || resources.length"
        class="space-y-3"
        data-testid="catalogue-context"
      >
        <div>
          <h2 class="text-sm font-semibold">Prompts and documents</h2>
          <p class="text-xs text-muted">
            Context this bundle offers on its own: prompts you can pick in your client, and
            documents it can read into the conversation.
          </p>
        </div>
        <div class="wf-card space-y-2">
          <ul class="divide-y divide-default">
            <li
              v-for="prompt in prompts"
              :key="`prompt-${prompt.name}`"
              class="py-2 first:pt-0 last:pb-0"
              :data-testid="`catalogue-prompt-${prompt.name}`"
            >
              <p class="inline-flex items-center gap-1.5 text-sm" :title="prompt.name">
                <UIcon name="i-lucide-message-square-text" class="size-4 text-muted" />{{
                  prompt.title || prompt.name
                }}
              </p>
              <p v-if="prompt.description" class="mt-1 text-xs text-toned">
                {{ prompt.description }}
              </p>
            </li>
            <li
              v-for="resource in resources"
              :key="`resource-${resource.name}`"
              class="py-2 first:pt-0 last:pb-0"
              :data-testid="`catalogue-resource-${resource.name}`"
            >
              <p class="inline-flex items-center gap-1.5 text-sm" :title="resource.name">
                <UIcon name="i-lucide-file-text" class="size-4 text-muted" />{{
                  resource.title || resource.name
                }}
              </p>
              <p v-if="resource.description" class="mt-1 text-xs text-toned">
                {{ resource.description }}
              </p>
            </li>
          </ul>
        </div>
      </div>

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
