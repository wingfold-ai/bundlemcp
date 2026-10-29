<script setup lang="ts">
/** Rows of header name and value, edited in place, with a button for one more. */
import type { HeaderRow } from "~/utils/headerRows";

const rows = defineModel<HeaderRow[]>({ required: true });

withDefaults(
  defineProps<{
    keyPlaceholder: string;
    valuePlaceholder: string;
    addLabel: string;
    /** "password" for values that must not be shown while typed, such as secrets. */
    valueType?: "text" | "password";
    /** Prefix of the rows' test ids (`<prefix>-key-0`, `<prefix>-add`); none without it. */
    testIdPrefix?: string;
  }>(),
  { valueType: "text", testIdPrefix: undefined },
);

function addRow() {
  rows.value = [...rows.value, { key: "", val: "" }];
}
</script>

<template>
  <div>
    <div v-for="(row, i) in rows" :key="i" class="flex gap-2 mb-1">
      <input
        v-model="row.key"
        class="wf-input"
        :placeholder="keyPlaceholder"
        :data-testid="testIdPrefix && `${testIdPrefix}-key-${i}`"
      />
      <input
        v-model="row.val"
        :type="valueType"
        class="wf-input"
        :placeholder="valuePlaceholder"
        :data-testid="testIdPrefix && `${testIdPrefix}-val-${i}`"
      />
    </div>
    <UButton
      size="xs"
      variant="soft"
      :data-testid="testIdPrefix && `${testIdPrefix}-add`"
      @click="addRow"
      >{{ addLabel }}</UButton
    >
  </div>
</template>
