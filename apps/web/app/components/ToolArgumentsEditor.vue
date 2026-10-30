<script setup lang="ts">
/**
 * A tool's call arguments, as a form built from its input schema or as raw
 * JSON, switchable both ways with the arguments carried across. A schema a
 * flat form cannot express is edited as raw JSON only.
 */
import type { components } from "~~/types/api";
import { formArguments, formFields, formValues, type FormField } from "~/utils/schemaForm";

const props = defineProps<{ tool: components["schemas"]["InspectorTool"] }>();
const emit = defineEmits<{ invalid: [message: string]; valid: [] }>();

const raw = ref(false);
const rawText = ref("{}");
const values = ref<Record<string, unknown>>({});
const fields = computed<FormField[] | null>(() => formFields(props.tool.input_schema));

watch(
  () => props.tool,
  (tool) => {
    values.value = {};
    rawText.value = "{}";
    raw.value = formFields(tool.input_schema) === null;
  },
  { immediate: true },
);

/** Switch between the form and raw JSON, carrying the arguments across. */
function toggleRaw() {
  const form = fields.value;
  if (!raw.value) {
    rawText.value = JSON.stringify(form ? formArguments(form, values.value) : {}, null, 2);
    raw.value = true;
    return;
  }
  if (!form) return;
  try {
    values.value = formValues(form, JSON.parse(rawText.value || "{}"));
    raw.value = false;
    emit("valid");
  } catch {
    emit("invalid", "The raw JSON is not valid; fix it before switching back to the form.");
  }
}

/** The arguments as entered, or null (with `invalid` emitted) when the raw JSON is not an object. */
function callArguments(): Record<string, unknown> | null {
  if (!raw.value && fields.value) return formArguments(fields.value, values.value);
  try {
    const parsed = JSON.parse(rawText.value || "{}");
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) return parsed;
  } catch {
    // reported below
  }
  emit("invalid", "The arguments must be a JSON object.");
  return null;
}

defineExpose({ callArguments });
</script>

<template>
  <div class="flex items-center gap-2">
    <h3 class="text-sm font-medium">Arguments</h3>
    <UButton size="xs" variant="ghost" :disabled="!fields" data-testid="inspector-raw-toggle" @click="toggleRaw">
      {{ raw ? "Form" : "Raw JSON" }}
    </UButton>
    <span v-if="!fields" class="text-xs text-toned">this schema needs raw JSON</span>
  </div>

  <textarea
    v-if="raw || !fields"
    v-model="rawText"
    rows="6"
    class="wf-input font-mono text-xs"
    data-testid="inspector-raw"
  />
  <div v-else class="space-y-2">
    <p v-if="!fields.length" class="text-sm text-toned">This tool takes no arguments.</p>
    <div v-for="field in fields" :key="field.name">
      <label class="wf-label">
        {{ field.name }}<span v-if="field.required" class="text-red-600"> *</span>
        <span class="text-toned font-normal"> {{ field.kind }}</span>
      </label>
      <select
        v-if="field.kind === 'enum'"
        v-model="values[field.name]"
        class="wf-input"
        :data-testid="`inspector-arg-${field.name}`"
      >
        <option v-for="o in field.options" :key="String(o)" :value="String(o)">{{ o }}</option>
      </select>
      <input
        v-else-if="field.kind === 'boolean'"
        v-model="values[field.name]"
        type="checkbox"
        :data-testid="`inspector-arg-${field.name}`"
      />
      <input
        v-else
        v-model="values[field.name]"
        :type="field.kind === 'string' ? 'text' : 'number'"
        :required="field.required"
        class="wf-input"
        :data-testid="`inspector-arg-${field.name}`"
      />
      <p v-if="field.description" class="text-xs text-toned">{{ field.description }}</p>
    </div>
  </div>
</template>
