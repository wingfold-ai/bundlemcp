<script setup lang="ts">
/**
 * The documents a bundle itself serves (BPR-6, BPR-14): list, edit one at a
 * time, and preview Markdown as a client would render it.
 */
import type { components } from "~~/types/api";

type BundleResourceRead = components["schemas"]["BundleResourceRead"];
type ResourceMimeType = components["schemas"]["ResourceMimeType"];

const props = defineProps<{ bundleName: string }>();
const emit = defineEmits<{ changed: [] }>();

const MIME_TYPES: ResourceMimeType[] = [
  "text/markdown",
  "text/plain",
  "text/csv",
  "application/json",
  "application/yaml",
];

const api = useApi();
const errorMsg = ref("");
const resources = ref<BundleResourceRead[]>([]);

// the open editor; `original` is the name being edited, "" for a new resource
const editing = ref(false);
const original = ref("");
const name = ref("");
const title = ref("");
const description = ref("");
const mimeType = ref<ResourceMimeType>("text/markdown");
const content = ref("");
const preview = ref(false);
const saving = ref(false);

const previewHtml = computed(() => renderMarkdown(content.value));
const contentBytes = computed(() => new TextEncoder().encode(content.value).length);

async function load() {
  const { data, error } = await api.GET("/api/v1/bundles/{bundle}/resources", {
    params: { path: { bundle: props.bundleName }, query: { offset: 0, limit: 200 } },
  });
  if (error) {
    errorMsg.value = apiErrorMessage(error);
    return;
  }
  resources.value = data.items;
}

function openEditor(resource?: BundleResourceRead) {
  errorMsg.value = "";
  original.value = resource?.name ?? "";
  name.value = resource?.name ?? "";
  title.value = resource?.title ?? "";
  description.value = resource?.description ?? "";
  mimeType.value = resource?.mime_type ?? "text/markdown";
  content.value = resource?.content ?? "";
  preview.value = false;
  editing.value = true;
}

async function save() {
  errorMsg.value = "";
  if (!BUNDLE_RESOURCE_NAME_RE.test(name.value)) {
    errorMsg.value = "Name: letters, digits, _ and -, with '/' between folders";
    return;
  }
  saving.value = true;
  try {
    const { error } = await api.PUT("/api/v1/bundles/{bundle}/resources/{name}", {
      params: { path: { bundle: props.bundleName, name: name.value } },
      body: {
        name: name.value,
        title: title.value || null,
        description: description.value || null,
        mime_type: mimeType.value,
        content: content.value,
      },
    });
    if (error) {
      errorMsg.value = apiErrorMessage(error);
      return;
    }
    editing.value = false;
    await load();
    emit("changed");
  } finally {
    saving.value = false;
  }
}

async function remove(resourceName: string) {
  if (!window.confirm(`Delete resource "${resourceName}"?`)) return;
  errorMsg.value = "";
  const { error } = await api.DELETE("/api/v1/bundles/{bundle}/resources/{name}", {
    params: { path: { bundle: props.bundleName, name: resourceName } },
  });
  if (error) {
    // 409 when a prompt still embeds it
    errorMsg.value = apiErrorMessage(error);
    return;
  }
  await load();
  emit("changed");
}

defineExpose({ load });
onMounted(load);
</script>

<template>
  <div class="wf-card space-y-3" data-testid="bundle-resources">
    <div>
      <h2 class="text-sm font-semibold">Resources</h2>
      <p class="wf-help">
        Documents this bundle serves itself — a style guide, worked examples, reference tables.
        Clients read them as <code>bundle://resources/&lt;name&gt;</code>; no upstream server is
        contacted. Not secret: every caller of the bundle's endpoints, and the model, can read
        them.
      </p>
    </div>

    <p v-if="errorMsg" class="text-red-600 text-sm" data-testid="resources-error">{{ errorMsg }}</p>

    <div class="overflow-x-auto">
      <table class="wf-table wf-table-controls" data-testid="resources-table">
        <thead>
          <tr>
            <th>Name</th>
            <th>Title</th>
            <th>Type</th>
            <th>Size</th>
            <th />
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in resources" :key="r.name" :data-testid="`resource-${r.name}`">
            <td class="font-mono">{{ r.name }}</td>
            <td>{{ r.title }}</td>
            <td>{{ r.mime_type }}</td>
            <td class="whitespace-nowrap">{{ r.size_bytes }} B</td>
            <td class="whitespace-nowrap space-x-1">
              <UButton
                size="xs"
                variant="soft"
                :data-testid="`resource-edit-${r.name}`"
                @click="openEditor(r)"
                >Edit</UButton
              >
              <UButton
                size="xs"
                color="error"
                variant="soft"
                :data-testid="`resource-delete-${r.name}`"
                @click="remove(r.name)"
                >Delete</UButton
              >
            </td>
          </tr>
          <tr v-if="resources.length === 0">
            <td colspan="5" class="text-muted">No resources of its own.</td>
          </tr>
        </tbody>
      </table>
    </div>

    <UButton
      v-if="!editing"
      size="sm"
      variant="soft"
      data-testid="resource-new"
      @click="openEditor()"
      >New resource</UButton
    >

    <form
      v-else
      class="space-y-3 border-t border-muted pt-4"
      data-testid="resource-editor"
      @submit.prevent="save"
    >
      <div class="grid gap-3 sm:grid-cols-2">
        <div>
          <label class="wf-label" for="resource-name">Name</label>
          <input
            id="resource-name"
            v-model="name"
            class="wf-input font-mono"
            :disabled="original !== ''"
            placeholder="guides/style"
            data-testid="resource-name"
          />
          <p class="wf-help">Unique in the bundle; "/" separates folders.</p>
        </div>
        <div>
          <label class="wf-label" for="resource-mime">Type</label>
          <select id="resource-mime" v-model="mimeType" class="wf-input" data-testid="resource-mime">
            <option v-for="m in MIME_TYPES" :key="m" :value="m">{{ m }}</option>
          </select>
        </div>
        <div>
          <label class="wf-label" for="resource-title">Title</label>
          <input id="resource-title" v-model="title" class="wf-input" data-testid="resource-title" />
        </div>
        <div>
          <label class="wf-label" for="resource-description">Description</label>
          <input
            id="resource-description"
            v-model="description"
            class="wf-input"
            data-testid="resource-description"
          />
        </div>
      </div>
      <div>
        <div class="flex items-center justify-between">
          <label class="wf-label" for="resource-content">Content</label>
          <label class="flex items-center gap-1 text-xs text-muted">
            <input v-model="preview" type="checkbox" data-testid="resource-preview-toggle" />
            Preview
          </label>
        </div>
        <textarea
          v-if="!preview"
          id="resource-content"
          v-model="content"
          rows="14"
          class="wf-input font-mono"
          data-testid="resource-content"
        />
        <!-- eslint-disable-next-line vue/no-v-html -- sanitized by renderMarkdown -->
        <div
          v-else-if="mimeType === 'text/markdown'"
          class="wf-markdown border border-default rounded-md p-3"
          data-testid="resource-preview"
          v-html="previewHtml"
        />
        <pre
          v-else
          class="border border-default rounded-md p-3 text-xs overflow-x-auto"
          data-testid="resource-preview"
          >{{ content }}</pre
        >
        <p class="wf-help">
          {{ contentBytes }} bytes; at most 256 KiB per resource and 4 MiB across the bundle.
        </p>
      </div>
      <div class="flex gap-2">
        <UButton type="submit" size="sm" :loading="saving" data-testid="resource-save"
          >Save resource</UButton
        >
        <UButton size="sm" variant="ghost" data-testid="resource-cancel" @click="editing = false"
          >Cancel</UButton
        >
      </div>
    </form>
  </div>
</template>
