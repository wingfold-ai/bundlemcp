<script setup lang="ts">
/** How the gateway speaks to an upstream: the protocol revision, and where its lists come from. */
import type { components } from "~~/types/api";

type Schemas = components["schemas"];

const protocolMode = defineModel<Schemas["ServerRead"]["protocol_mode"]>("protocolMode", {
  required: true,
});
const listingSnapshot = defineModel<Schemas["ListingSnapshotMode"]>("listingSnapshot", {
  required: true,
});

/** Prefix of the fields' ids and test ids: `<prefix>-protocol-mode`, `<prefix>-listing-snapshot`. */
defineProps<{ idPrefix: string }>();
</script>

<template>
  <div class="space-y-3">
    <div>
      <label class="wf-label" :for="`${idPrefix}-protocol-mode`">Protocol</label>
      <select
        :id="`${idPrefix}-protocol-mode`"
        v-model="protocolMode"
        class="wf-input"
        :data-testid="`${idPrefix}-protocol-mode`"
      >
        <option value="auto">auto — negotiate (recommended)</option>
        <option value="session">session — always the initialize handshake</option>
        <option value="2026-07-28">pin 2026-07-28</option>
      </select>
    </div>
    <div>
      <label class="wf-label" :for="`${idPrefix}-listing-snapshot`">Prompt and resource lists</label>
      <select
        :id="`${idPrefix}-listing-snapshot`"
        v-model="listingSnapshot"
        class="wf-input"
        :data-testid="`${idPrefix}-listing-snapshot`"
      >
        <option value="auto">auto — stored listing when it is the same for every caller</option>
        <option value="shared">shared — stored listing for every caller</option>
        <option value="live">live — always ask the server</option>
      </select>
      <p class="wf-help">
        Lists served from what discovery stored leave a server that scales to zero asleep
        when a client connects. Choose shared when the server is sent the caller's identity
        but lists the same prompts and resources for everyone.
      </p>
    </div>
  </div>
</template>
