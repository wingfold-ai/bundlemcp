<script setup lang="ts">
/** One tool of the connected server: what it says about itself, its arguments, and a streamed call. */
import type { components } from "~~/types/api";

type Schemas = components["schemas"];

const props = defineProps<{
  tool: Schemas["InspectorTool"];
  /** The target the shown connection was made to; a call reuses it, not the edited inputs. */
  target: Schemas["InspectorRequest"]["target"];
}>();
/** The message to show at the page's error, or null to clear it. */
const emit = defineEmits<{ error: [message: string | null] }>();

const argumentsEditor = useTemplateRef("argumentsEditor");
const { calling, progress, outcome, failure, reset, call: callTool } = useToolCall();
const destructive = computed(() => props.tool.annotations?.destructiveHint === true);

watch(() => props.tool, reset);

async function call() {
  const args = argumentsEditor.value?.callArguments();
  if (!args) return;
  const name = props.tool.name;
  if (destructive.value && !window.confirm(`"${name}" says it may change or delete data. Call it?`)) {
    return;
  }
  emit("error", null);
  emit("error", await callTool(props.target, name, args));
}

function pretty(value: unknown): string {
  return JSON.stringify(value, null, 2);
}
</script>

<template>
  <div class="wf-card space-y-3" data-testid="inspector-tool">
    <div>
      <h2 class="font-medium">{{ tool.title || tool.name }}</h2>
      <p v-if="tool.description" class="text-sm text-toned whitespace-pre-wrap">{{ tool.description }}</p>
      <div v-if="tool.annotations" class="flex gap-2 mt-1">
        <UBadge v-for="(v, k) in tool.annotations" :key="k" variant="subtle" :color="v === true ? 'primary' : 'neutral'">
          {{ k }}: {{ v }}
        </UBadge>
      </div>
    </div>

    <details>
      <summary class="text-sm cursor-pointer">Input schema</summary>
      <pre class="text-xs overflow-auto" data-testid="inspector-schema">{{ pretty(tool.input_schema) }}</pre>
    </details>

    <ToolArgumentsEditor
      ref="argumentsEditor"
      :tool="tool"
      @invalid="(message) => emit('error', message)"
      @valid="emit('error', null)"
    />

    <UButton :loading="calling" :color="destructive ? 'error' : 'primary'" data-testid="inspector-call" @click="call">
      Call {{ tool.name }}
    </UButton>

    <ol v-if="progress.length" class="text-sm space-y-1" data-testid="inspector-progress">
      <li v-for="(p, i) in progress" :key="i" data-testid="inspector-progress-item">
        <span class="tabular-nums text-toned">+{{ p.elapsed_ms }} ms</span>
        {{ p.progress }}<span v-if="p.total != null">/{{ p.total }}</span>
        <span v-if="p.message"> — {{ p.message }}</span>
      </li>
    </ol>

    <div v-if="failure" class="text-sm text-red-600" data-testid="inspector-failure">
      {{ failure.connection_state }}: {{ failure.detail }}
    </div>

    <div v-if="outcome" data-testid="inspector-outcome" :data-error="outcome.is_error">
      <p class="text-sm" :class="outcome.is_error ? 'text-red-600' : 'text-toned'">
        {{ outcome.is_error ? "Error" : "Result" }} in
        <span data-testid="inspector-duration">{{ outcome.duration_ms }} ms</span>
        (connecting: {{ outcome.initialize_ms }} ms)
      </p>
      <p v-if="outcome.error_message" class="text-sm text-red-600" data-testid="inspector-error">
        {{ outcome.error_code }}: {{ outcome.error_message }}
      </p>
      <pre v-if="outcome.result" class="text-xs overflow-auto max-h-96" data-testid="inspector-result">{{ pretty(outcome.result) }}</pre>
    </div>
  </div>
</template>
