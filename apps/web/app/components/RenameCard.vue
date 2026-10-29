<script setup lang="ts">
/**
 * Renaming a bundle, upstream or endpoint: the new name is checked while it is
 * typed, against the published rules and the names already taken, and the
 * consequence of the rename is shown before it is sent. Ticking the
 * acknowledgement sends `force`; it resets whenever the new name changes,
 * since a different name is a different consequence.
 */
type RenamedResource = Extract<NamedResource, "bundle" | "upstream" | "endpoint">;

const props = withDefaults(
  defineProps<{
    kind: RenamedResource;
    current: string;
    /** The names a rename would collide with: every resource of the kind but this one. */
    taken: string[];
    /** The text of the acknowledgement checkbox. */
    acknowledgement: string;
    /** Whether the rename waits for the acknowledgement; without it, ticking only sends `force`. */
    requireAcknowledgement?: boolean;
    /** A heading of its own, for a rename that is a card by itself rather than part of one. */
    heading?: string;
    label?: string;
    placeholder?: string;
    /** Prefix of the control's test ids: `<prefix>-input`, `-hint`, `-ack` and `-submit`. */
    testIdPrefix?: string;
    acknowledgementTestId?: string;
  }>(),
  {
    requireAcknowledgement: false,
    heading: undefined,
    label: "New name",
    placeholder: "new name",
    testIdPrefix: "rename",
    acknowledgementTestId: undefined,
  },
);

defineSlots<{
  /** What the rename changes, shown once a new name is typed. */
  consequence(props: { newName: string }): unknown;
}>();

const emit = defineEmits<{ started: []; renamed: [newName: string] }>();

const api = useApi();
const input = ref("");
const acknowledged = ref(false);
const newName = computed(() => input.value.trim());
const renaming = computed(() => newName.value !== "" && newName.value !== props.current);
const hint = computed(() =>
  renaming.value ? nameProblem(props.kind, newName.value, props.taken) : null,
);
const blocked = computed(
  () => !renaming.value || Boolean(hint.value) || (props.requireAcknowledgement && !acknowledged.value),
);

watch(input, () => {
  acknowledged.value = false;
});

function send(name: string, query: { new_name: string; force: boolean }) {
  const path = { name };
  switch (props.kind) {
    case "bundle":
      return api.POST("/api/v1/bundles/{name}:rename", { params: { path, query } });
    case "upstream":
      return api.POST("/api/v1/upstreams/{name}:rename", { params: { path, query } });
    case "endpoint":
      return api.POST("/api/v1/endpoints/{name}:rename", { params: { path, query } });
  }
}

const { run, busy, error } = useAction(async () => {
  const problem = nameProblem(props.kind, newName.value, props.taken);
  if (problem) throw new ValidationProblem(problem);
  return await send(props.current, { new_name: newName.value, force: acknowledged.value });
});

async function submit() {
  const target = newName.value;
  emit("started");
  if (!(await run())) return;
  input.value = "";
  emit("renamed", target);
}
/** Forget the last rename's error, as starting another action of the same card does. */
function clearError() {
  error.value = "";
}

defineExpose({ clearError });
</script>

<template>
  <form class="space-y-2" @submit.prevent="submit">
    <h2 v-if="heading" class="text-sm font-semibold">{{ heading }}</h2>
    <div>
      <label class="wf-label" :for="`${testIdPrefix}-input`">{{ label }}</label>
      <input
        :id="`${testIdPrefix}-input`"
        v-model="input"
        class="wf-input"
        :placeholder="placeholder"
        :data-testid="`${testIdPrefix}-input`"
      />
      <p v-if="hint" class="text-red-600 text-xs mt-1" :data-testid="`${testIdPrefix}-hint`">
        {{ hint }}
      </p>
    </div>
    <div v-if="renaming" class="space-y-2 text-sm">
      <slot name="consequence" :new-name="newName" />
      <label class="flex items-center gap-2">
        <input
          v-model="acknowledged"
          type="checkbox"
          :data-testid="acknowledgementTestId ?? `${testIdPrefix}-ack`"
        />
        {{ acknowledgement }}
      </label>
    </div>
    <p v-if="error" class="text-red-600 text-sm" data-testid="error">
      {{ error }}
    </p>
    <UButton
      type="submit"
      size="sm"
      variant="outline"
      color="error"
      :loading="busy"
      :disabled="blocked"
      :data-testid="`${testIdPrefix}-submit`"
    >
      Rename
    </UButton>
  </form>
</template>
