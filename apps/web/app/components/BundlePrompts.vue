<script setup lang="ts">
/**
 * The prompts a bundle itself serves: list, edit one at a time,
 * and preview it rendered with sample arguments, as prompts/get would.
 */
import type { components } from "~~/types/api";

type BundlePromptRead = components["schemas"]["BundlePromptRead"];
type PromptRole = components["schemas"]["PromptRole"];

interface ArgumentDraft {
  name: string;
  description: string;
  required: boolean;
  values: string; // comma-separated in the form, a list on the wire
}
interface MessageDraft {
  role: PromptRole;
  kind: "text" | "resource";
  text: string;
  resource: string;
}

const props = defineProps<{ bundleName: string }>();

const api = useApi();
const errorMsg = ref("");
const prompts = ref<BundlePromptRead[]>([]);
const resourceNames = ref<string[]>([]);

const editing = ref(false);
const original = ref("");
const name = ref("");
const title = ref("");
const description = ref("");
const args = ref<ArgumentDraft[]>([]);
const messages = ref<MessageDraft[]>([]);
const samples = ref<Record<string, string>>({});
const saving = ref(false);

async function load() {
  const [promptList, resourceList] = await Promise.all([
    api.GET("/api/v1/bundles/{bundle}/prompts", {
      params: { path: { bundle: props.bundleName }, query: { offset: 0, limit: 100 } },
    }),
    api.GET("/api/v1/bundles/{bundle}/resources", {
      params: { path: { bundle: props.bundleName }, query: { offset: 0, limit: 200 } },
    }),
  ]);
  if (promptList.error || resourceList.error) {
    errorMsg.value = apiErrorMessage(promptList.error ?? resourceList.error);
    return;
  }
  prompts.value = promptList.data.items;
  resourceNames.value = resourceList.data.items.map((r) => r.name);
}

function openEditor(prompt?: BundlePromptRead) {
  errorMsg.value = "";
  original.value = prompt?.name ?? "";
  name.value = prompt?.name ?? "";
  title.value = prompt?.title ?? "";
  description.value = prompt?.description ?? "";
  args.value = (prompt?.arguments ?? []).map((a) => ({
    name: a.name,
    description: a.description ?? "",
    required: a.required ?? false,
    values: (a.values ?? []).join(", "),
  }));
  messages.value = (prompt?.messages ?? [{ role: "user", text: "", resource: null }]).map(
    (m) => ({
      role: m.role,
      kind: m.resource ? "resource" : "text",
      text: m.text ?? "",
      resource: m.resource ?? "",
    }),
  );
  samples.value = {};
  editing.value = true;
}

function addArgument() {
  args.value.push({ name: "", description: "", required: false, values: "" });
}

function addMessage(kind: MessageDraft["kind"]) {
  messages.value.push({ role: "user", kind, text: "", resource: resourceNames.value[0] ?? "" });
}

// placeholders the text uses but no argument declares; the gateway would refuse them
const undeclared = computed(() => {
  const declared = new Set(args.value.map((a) => a.name));
  const used = messages.value.flatMap((m) => (m.kind === "text" ? promptPlaceholders(m.text) : []));
  return [...new Set(used)].filter((n) => !declared.has(n));
});

const rendered = computed(() =>
  messages.value.map((m) => ({
    role: m.role,
    kind: m.kind,
    text: m.kind === "text" ? renderPromptText(m.text, samples.value) : m.resource,
  })),
);

async function save() {
  errorMsg.value = "";
  if (!PROMPT_NAME_RE.test(name.value)) {
    errorMsg.value = "Name: letters, digits, _ and -, and never '__'";
    return;
  }
  saving.value = true;
  try {
    const { error } = await api.PUT("/api/v1/bundles/{bundle}/prompts/{name}", {
      params: { path: { bundle: props.bundleName, name: name.value } },
      body: {
        name: name.value,
        title: title.value || null,
        description: description.value || null,
        arguments: args.value.map((a) => ({
          name: a.name,
          description: a.description || null,
          required: a.required,
          values: a.values
            .split(",")
            .map((v) => v.trim())
            .filter(Boolean),
        })),
        messages: messages.value.map((m) =>
          m.kind === "text"
            ? { role: m.role, text: m.text, resource: null }
            : { role: m.role, text: null, resource: m.resource },
        ),
      },
    });
    if (error) {
      errorMsg.value = apiErrorMessage(error);
      return;
    }
    editing.value = false;
    await load();
  } finally {
    saving.value = false;
  }
}

async function remove(promptName: string) {
  if (!window.confirm(`Delete prompt "${promptName}"?`)) return;
  errorMsg.value = "";
  const { error } = await api.DELETE("/api/v1/bundles/{bundle}/prompts/{name}", {
    params: { path: { bundle: props.bundleName, name: promptName } },
  });
  if (error) {
    errorMsg.value = apiErrorMessage(error);
    return;
  }
  await load();
}

defineExpose({ load });
onMounted(load);
</script>

<template>
  <div class="wf-card space-y-3" data-testid="bundle-prompts">
    <div>
      <h2 class="text-sm font-semibold">Prompts</h2>
      <p class="wf-help">
        Message templates this bundle serves itself, listed before the upstream servers' prompts
        and named without a server prefix. Use them to tell the model how this bundle's tools are
        meant to be used. Text may refer to an argument as <code v-pre>{{argument}}</code>. Not
        secret: every caller of the bundle's endpoints, and the model, can read them.
      </p>
    </div>

    <p v-if="errorMsg" class="text-red-600 text-sm" data-testid="prompts-error">{{ errorMsg }}</p>

    <div class="overflow-x-auto">
      <table class="wf-table wf-table-controls" data-testid="prompts-table">
        <thead>
          <tr>
            <th>Name</th>
            <th>Title</th>
            <th>Arguments</th>
            <th>Messages</th>
            <th />
          </tr>
        </thead>
        <tbody>
          <tr v-for="p in prompts" :key="p.name" :data-testid="`prompt-${p.name}`">
            <td class="font-mono">{{ p.name }}</td>
            <td>{{ p.title }}</td>
            <td>{{ p.arguments.map((a) => a.name).join(", ") }}</td>
            <td>{{ p.messages.length }}</td>
            <td class="whitespace-nowrap space-x-1">
              <UButton
                size="xs"
                variant="soft"
                :data-testid="`prompt-edit-${p.name}`"
                @click="openEditor(p)"
                >Edit</UButton
              >
              <UButton
                size="xs"
                color="error"
                variant="soft"
                :data-testid="`prompt-delete-${p.name}`"
                @click="remove(p.name)"
                >Delete</UButton
              >
            </td>
          </tr>
          <tr v-if="prompts.length === 0">
            <td colspan="5" class="text-muted">No prompts of its own.</td>
          </tr>
        </tbody>
      </table>
    </div>

    <UButton v-if="!editing" size="sm" variant="soft" data-testid="prompt-new" @click="openEditor()"
      >New prompt</UButton
    >

    <form
      v-else
      class="space-y-4 border-t border-muted pt-4"
      data-testid="prompt-editor"
      @submit.prevent="save"
    >
      <div class="grid gap-3 sm:grid-cols-3">
        <div>
          <label class="wf-label" for="prompt-name">Name</label>
          <input
            id="prompt-name"
            v-model="name"
            class="wf-input font-mono"
            :disabled="original !== ''"
            data-testid="prompt-name"
          />
        </div>
        <div>
          <label class="wf-label" for="prompt-title">Title</label>
          <input id="prompt-title" v-model="title" class="wf-input" data-testid="prompt-title" />
        </div>
        <div>
          <label class="wf-label" for="prompt-description">Description</label>
          <input
            id="prompt-description"
            v-model="description"
            class="wf-input"
            data-testid="prompt-description"
          />
        </div>
      </div>

      <div class="space-y-2">
        <span class="wf-label">Arguments</span>
        <div
          v-for="(a, i) in args"
          :key="i"
          class="grid gap-2 sm:grid-cols-[1fr_2fr_2fr_auto_auto] items-center"
          :data-testid="`prompt-argument-${i}`"
        >
          <input v-model="a.name" class="wf-input font-mono" placeholder="name" />
          <input v-model="a.description" class="wf-input" placeholder="description" />
          <input
            v-model="a.values"
            class="wf-input"
            placeholder="suggested values, comma-separated"
          />
          <label class="flex items-center gap-1 text-xs">
            <input v-model="a.required" type="checkbox" /> required
          </label>
          <UButton size="xs" color="error" variant="ghost" @click="args.splice(i, 1)"
            >Remove</UButton
          >
        </div>
        <UButton size="xs" variant="soft" data-testid="prompt-add-argument" @click="addArgument"
          >Add argument</UButton
        >
      </div>

      <div class="space-y-2">
        <span class="wf-label">Messages</span>
        <div
          v-for="(m, i) in messages"
          :key="i"
          class="flex flex-col sm:flex-row sm:items-start gap-2"
          :data-testid="`prompt-message-${i}`"
        >
          <div class="sm:w-32 shrink-0">
            <select v-model="m.role" class="wf-input" aria-label="Role">
              <option value="user">user</option>
              <option value="assistant">assistant</option>
            </select>
          </div>
          <textarea
            v-if="m.kind === 'text'"
            v-model="m.text"
            rows="4"
            class="wf-input font-mono"
            :data-testid="`prompt-message-text-${i}`"
          />
          <select
            v-else
            v-model="m.resource"
            class="wf-input font-mono"
            :data-testid="`prompt-message-resource-${i}`"
          >
            <option v-for="r in resourceNames" :key="r" :value="r">embeds {{ r }}</option>
          </select>
          <UButton size="xs" color="error" variant="ghost" @click="messages.splice(i, 1)"
            >Remove</UButton
          >
        </div>
        <div class="flex gap-2">
          <UButton size="xs" variant="soft" data-testid="prompt-add-text" @click="addMessage('text')"
            >Add text message</UButton
          >
          <UButton
            size="xs"
            variant="soft"
            :disabled="resourceNames.length === 0"
            title="Embeds one of this bundle's resources in full"
            data-testid="prompt-add-resource"
            @click="addMessage('resource')"
            >Embed a resource</UButton
          >
        </div>
        <p v-if="undeclared.length" class="text-amber-600 text-sm" data-testid="prompt-undeclared">
          Not declared as arguments: {{ undeclared.join(", ") }}
        </p>
      </div>

      <div class="space-y-2 border border-default rounded-md p-3" data-testid="prompt-preview">
        <span class="wf-label">Preview with sample arguments</span>
        <div v-if="args.length" class="grid gap-2 sm:grid-cols-3">
          <div v-for="a in args.filter((x) => x.name)" :key="a.name">
            <label class="wf-label font-mono" :for="`prompt-sample-${a.name}`">{{ a.name }}</label>
            <input
              :id="`prompt-sample-${a.name}`"
              v-model="samples[a.name]"
              class="wf-input"
              :data-testid="`prompt-sample-${a.name}`"
            />
          </div>
        </div>
        <div v-for="(r, i) in rendered" :key="i" class="text-sm">
          <span class="text-xs font-medium text-muted">{{ r.role }}</span>
          <p v-if="r.kind === 'text'" class="whitespace-pre-wrap" :data-testid="`prompt-rendered-${i}`">
            {{ r.text }}
          </p>
          <p v-else class="text-muted italic">embeds resource {{ r.text }}</p>
        </div>
      </div>

      <div class="flex gap-2">
        <UButton type="submit" size="sm" :loading="saving" data-testid="prompt-save"
          >Save prompt</UButton
        >
        <UButton size="sm" variant="ghost" data-testid="prompt-cancel" @click="editing = false"
          >Cancel</UButton
        >
      </div>
    </form>
  </div>
</template>
