<script setup lang="ts">
/** What checking an upstream's URL found: its state, who it is, and how it signs in. */
import type { components } from "~~/types/api";

defineProps<{ inspection: components["schemas"]["ServerInspection"] }>();
</script>

<template>
  <div class="rounded-md border border-default p-3 space-y-2 text-sm" data-testid="inspection">
    <div class="flex flex-wrap items-center gap-2">
      <UBadge
        :icon="CONNECTION_STATE_ICON[inspection.connection_state]"
        :color="connectionStateColor(inspection.connection_state)"
        variant="subtle"
        data-testid="inspection-state"
        >{{ CONNECTION_STATE_LABEL[inspection.connection_state] }}</UBadge
      >
      <span v-if="inspection.server_info" class="font-medium">
        {{ inspection.server_info.title || inspection.server_info.name }}
      </span>
      <span v-if="inspection.protocol_version" class="text-muted">
        MCP {{ inspection.protocol_version }}
      </span>
      <span v-if="inspection.tool_names?.length" class="text-muted">
        · {{ inspection.tool_names.length }}
        {{ inspection.tool_names.length === 1 ? "tool" : "tools" }}
      </span>
    </div>
    <p v-if="inspection.server_info?.description" class="text-muted">
      {{ inspection.server_info.description }}
    </p>
    <p v-if="inspection.detail" class="text-muted">{{ inspection.detail }}</p>
    <p v-if="inspection.oauth?.issuer" class="text-muted">
      Signs in at <code>{{ inspection.oauth.issuer }}</code>
      <span v-if="inspection.oauth.scopes?.length">, scopes {{ inspection.oauth.scopes.join(" ") }}</span>
    </p>
    <ul v-if="inspection.hints?.length" class="list-disc pl-5 space-y-1">
      <li v-for="h in inspection.hints" :key="h">{{ h }}</li>
    </ul>
  </div>
</template>
