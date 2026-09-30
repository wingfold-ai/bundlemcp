<script setup lang="ts">
/**
 * A server timestamp shown as local "YYYY-MM-DD HH:mm". The API's full ISO
 * value (UTC, microseconds) stays in the tooltip and the `datetime` attribute.
 */
const props = defineProps<{ value: string | null | undefined; empty?: string }>();

const pad = (n: number) => String(n).padStart(2, "0");

const label = computed(() => {
  if (!props.value) return props.empty ?? "—";
  const d = new Date(props.value);
  if (Number.isNaN(d.getTime())) return props.value;
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
    `${pad(d.getHours())}:${pad(d.getMinutes())}`
  );
});
</script>

<template>
  <time
    v-if="value"
    :datetime="value"
    :title="value"
    class="whitespace-nowrap tabular-nums"
    >{{ label }}</time
  >
  <span v-else class="text-muted">{{ label }}</span>
</template>
