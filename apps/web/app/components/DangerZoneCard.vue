<script setup lang="ts">
/** Renaming and deleting an upstream or an endpoint: the changes other systems notice. */
type DangerousResource = Extract<NamedResource, "upstream" | "endpoint">;

const props = defineProps<{
  kind: DangerousResource;
  current: string;
  /** The names a rename would collide with: every resource of the kind but this one. */
  taken: string[];
  renameLabel: string;
  /** The text of the rename's acknowledgement checkbox. */
  acknowledgement: string;
  requireAcknowledgement?: boolean;
  acknowledgementTestId?: string;
  deleteLabel: string;
  deleteTestId: string;
}>();

defineSlots<{
  /** What the rename changes, shown once a new name is typed. */
  consequence(props: { newName: string }): unknown;
}>();

const emit = defineEmits<{ renamed: [newName: string]; deleted: [] }>();

const api = useApi();
const renameCard = useTemplateRef("renameCard");

const { run, error } = useCardAction();

function send() {
  const params = { path: { name: props.current } };
  switch (props.kind) {
    case "upstream":
      return api.DELETE("/api/v1/upstreams/{name}", { params });
    case "endpoint":
      return api.DELETE("/api/v1/endpoints/{name}", { params });
  }
}

async function remove() {
  if (!window.confirm(`Delete ${props.kind} "${props.current}"?`)) return;
  renameCard.value?.clearError();
  if (await run(send)) emit("deleted");
}
</script>

<template>
  <div class="wf-card space-y-3 max-w-2xl" data-testid="card-danger">
    <h2 class="text-sm font-semibold">Danger zone</h2>
    <RenameCard
      ref="renameCard"
      :kind="kind"
      :current="current"
      :taken="taken"
      :label="renameLabel"
      :acknowledgement="acknowledgement"
      :require-acknowledgement="requireAcknowledgement"
      :acknowledgement-test-id="acknowledgementTestId"
      @started="error = ''"
      @renamed="(newName) => emit('renamed', newName)"
    >
      <template #consequence="{ newName }">
        <slot name="consequence" :new-name="newName" />
      </template>
    </RenameCard>
    <p v-if="error" class="text-red-600 text-sm" data-testid="error">{{ error }}</p>
    <UButton size="sm" color="error" :data-testid="deleteTestId" @click="remove">
      {{ deleteLabel }}
    </UButton>
  </div>
</template>
