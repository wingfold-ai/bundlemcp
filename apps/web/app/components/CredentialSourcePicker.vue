<script setup lang="ts">
/**
 * Where an upstream's credential comes from, with the detected answer marked,
 * and what that source needs: a key or token header, or an OAuth client.
 */
import type { components } from "~~/types/api";

type ServerInspection = components["schemas"]["ServerInspection"];

const source = defineModel<CredentialSource>("source", { required: true });
const presetIndex = defineModel<number>("presetIndex", { required: true });
const headerName = defineModel<string>("headerName", { required: true });
const headerValue = defineModel<string>("headerValue", { required: true });
const clientId = defineModel<string>("clientId", { required: true });
const clientSecret = defineModel<string>("clientSecret", { required: true });

const props = defineProps<{
  /** The source the inspection points to, marked as detected; null before a check. */
  detected: CredentialSource | null;
  inspection: ServerInspection | null;
  /** The answer to the last credential test. */
  verified: "" | "ok" | "refused";
  verifying: boolean;
  /** Whether the provider needs an OAuth client an admin registered. */
  needsManualClient: boolean;
  /** What the server's publisher says about the header being filled in. */
  headerHelp: string | null;
}>();

defineEmits<{ verify: [] }>();

const oauth = computed(() => props.inspection?.oauth ?? null);
const isOAuth = computed(() =>
  ["per_user", "shared_oauth", "client_credentials"].includes(source.value),
);
const callbackUrl = upstreamCallbackUrl();

function choosePreset(index: number) {
  presetIndex.value = index;
  const preset = CREDENTIAL_HEADER_PRESETS[index];
  if (preset?.name) headerName.value = preset.name;
}
</script>

<template>
  <fieldset class="space-y-2" data-testid="credential-source">
    <legend class="wf-label">Where does the credential come from?</legend>
    <label
      v-for="option in CREDENTIAL_SOURCES"
      :key="option.value"
      class="flex gap-2 items-start text-sm cursor-pointer"
    >
      <input
        v-model="source"
        type="radio"
        name="credential-source"
        :value="option.value"
        class="mt-1"
        :data-testid="`source-${option.value}`"
      />
      <span>
        <span class="font-medium">{{ option.label }}</span>
        <span v-if="detected === option.value" class="ml-1 text-xs text-primary">detected</span>
        <span class="block wf-help mt-0">{{ option.help }}</span>
      </span>
    </label>
  </fieldset>

  <!-- a key or token -->
  <div v-if="source === 'key'" class="space-y-2">
    <div class="grid gap-2 sm:grid-cols-3">
      <div>
        <label class="wf-label" for="create-header-preset">Header</label>
        <select
          id="create-header-preset"
          class="wf-input"
          :value="presetIndex"
          data-testid="create-header-preset"
          @change="choosePreset(Number(($event.target as HTMLSelectElement).value))"
        >
          <option v-for="(p, i) in CREDENTIAL_HEADER_PRESETS" :key="p.label" :value="i">
            {{ p.label }}
          </option>
        </select>
      </div>
      <div>
        <label class="wf-label" for="create-header-name">Header name</label>
        <input id="create-header-name" v-model="headerName" class="wf-input" data-testid="create-header-name" />
      </div>
      <div>
        <label class="wf-label" for="create-header-value">Key or token</label>
        <input
          id="create-header-value"
          v-model="headerValue"
          type="password"
          class="wf-input"
          autocomplete="off"
          data-testid="create-header-value"
        />
      </div>
    </div>
    <div class="flex items-center gap-2 text-sm">
      <UButton size="xs" variant="soft" :loading="verifying" data-testid="create-verify" @click="$emit('verify')"
        >Test the credential</UButton
      >
      <span v-if="verified === 'ok'" class="text-success">The upstream accepted it.</span>
      <span v-else-if="verified === 'refused'" class="text-error">
        The upstream refused it ({{ CONNECTION_STATE_LABEL[inspection?.connection_state ?? "error"] }}).
      </span>
    </div>
    <p v-if="headerHelp" class="wf-help" data-testid="create-header-help">{{ headerHelp }}</p>
    <p class="wf-help">Stored write-only: the value is never shown again.</p>
  </div>

  <!-- an OAuth client an admin must provide -->
  <div v-if="needsManualClient" class="space-y-2">
    <p class="wf-help mt-0">
      <template v-if="source === 'client_credentials'">
        Enter the client the provider issued for machine access.
      </template>
      <template v-else>
        The provider offers no automatic client registration. Register a client there with
        the redirect URI <code>{{ callbackUrl }}</code> and enter it here.
      </template>
    </p>
    <div class="grid gap-2 sm:grid-cols-2">
      <div>
        <label class="wf-label" for="create-client-id">Client ID</label>
        <input id="create-client-id" v-model="clientId" class="wf-input" data-testid="create-client-id" />
      </div>
      <div>
        <label class="wf-label" for="create-client-secret">Client secret</label>
        <input
          id="create-client-secret"
          v-model="clientSecret"
          type="password"
          class="wf-input"
          autocomplete="off"
          data-testid="create-client-secret"
        />
      </div>
    </div>
  </div>
  <p v-else-if="isOAuth && oauth?.client_identification" class="wf-help mt-0">
    The gateway identifies itself to the provider automatically
    ({{ oauth.client_identification === "metadata_document" ? "client metadata document" : "dynamic registration" }}).
  </p>
</template>
