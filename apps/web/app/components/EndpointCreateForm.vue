<script setup lang="ts">
/** A new endpoint serving a bundle: its name, profile and auth modes. */
import type { components } from "~~/types/api";

type EndpointProfile = components["schemas"]["EndpointProfile"];
type EndpointAuthMode = components["schemas"]["EndpointAuthMode"];
type EndpointProfileRead = components["schemas"]["EndpointProfileRead"];

const props = defineProps<{
  bundleName: string;
  /** Every endpoint's name, so a taken one is reported before anything is sent. */
  taken: string[];
  profiles: EndpointProfileRead[];
}>();

const api = useApi();
const createName = ref("");
const createProfile = ref<EndpointProfile>("default");
const createAuthModes = ref<EndpointAuthMode[]>(["oauth"]);
const allowUnauthenticated = ref(false);

const profileWarning = computed(
  () => props.profiles.find((p) => p.name === createProfile.value)?.warning ?? "",
);

// shown while typing, so a bad, reserved or taken name is seen before anything is sent
const createNameHint = computed(() =>
  createName.value ? nameProblem("endpoint", createName.value, props.taken) : null,
);

function toggleAuthMode(mode: EndpointAuthMode, checked: boolean) {
  if (checked) {
    // Client-side rule: "none" only alone.
    if (mode === "none") {
      createAuthModes.value = ["none"];
    } else {
      createAuthModes.value = [
        ...createAuthModes.value.filter((m) => m !== "none" && m !== mode),
        mode,
      ];
    }
  } else {
    createAuthModes.value = createAuthModes.value.filter((m) => m !== mode);
  }
}

function validateCreate(): void {
  const problem = nameProblem("endpoint", createName.value, props.taken);
  if (problem) throw new ValidationProblem(problem);
  const modes = createAuthModes.value;
  if (modes.length === 0) throw new ValidationProblem("Select at least one auth mode");
  if (modes.includes("none") && modes.length > 1) {
    throw new ValidationProblem('Auth mode "none" cannot be combined with other modes');
  }
  if (modes.includes("none") && !allowUnauthenticated.value) {
    throw new ValidationProblem(
      'Auth mode "none" requires "allow unauthenticated" to be checked',
    );
  }
}

const { run, error } = useAction(
  async () => {
    validateCreate();
    return await api.PUT("/api/v1/endpoints/{name}", {
      params: { path: { name: createName.value } },
      body: {
        name: createName.value,
        bundle_name: props.bundleName,
        profile: createProfile.value,
        auth_modes: createAuthModes.value,
        allow_unauthenticated: allowUnauthenticated.value,
        enabled: true,
      },
    });
  },
  {
    invalidates: () => [queryKeys.endpoints, queryKeys.bundle(props.bundleName), queryKeys.catalogue],
  },
);

async function createEndpoint() {
  if (await run()) createName.value = "";
}
</script>

<template>
  <form class="space-y-3 max-w-xl border-t border-muted pt-4" @submit.prevent="createEndpoint">
    <h3 class="text-sm font-medium">Create endpoint</h3>
    <div>
      <label class="wf-label" for="create-endpoint-name">Name (becomes the URL path)</label>
      <input
        id="create-endpoint-name"
        v-model="createName"
        class="wf-input"
        data-testid="create-endpoint-name"
      />
      <p v-if="createNameHint" class="text-red-600 text-xs mt-1" data-testid="create-endpoint-name-hint">
        {{ createNameHint }}
      </p>
    </div>
    <div>
      <label class="wf-label" for="create-endpoint-profile">Profile</label>
      <select
        id="create-endpoint-profile"
        v-model="createProfile"
        class="wf-input"
        data-testid="create-endpoint-profile"
      >
        <option v-for="p in profiles" :key="p.name" :value="p.name">
          {{ p.name }}<template v-if="p.description"> — {{ p.description }}</template>
        </option>
      </select>
      <p v-if="profileWarning" class="text-amber-600 text-sm mt-1" data-testid="profile-warning">
        {{ profileWarning }}
      </p>
    </div>
    <div>
      <span class="wf-label">Auth modes</span>
      <div class="flex gap-4 text-sm">
        <label v-for="mode in ['oauth', 'api_key', 'none'] as const" :key="mode" class="flex items-center gap-1">
          <input
            type="checkbox"
            :data-testid="`auth-mode-${mode}`"
            :checked="createAuthModes.includes(mode)"
            @change="toggleAuthMode(mode, ($event.target as HTMLInputElement).checked)"
          />
          {{ mode }}
        </label>
      </div>
    </div>
    <label class="flex items-center gap-1 text-sm">
      <input v-model="allowUnauthenticated" type="checkbox" data-testid="allow-unauthenticated" />
      Allow unauthenticated access (required for auth mode "none")
    </label>
    <p v-if="error" class="text-red-600 text-sm" data-testid="error">{{ error }}</p>
    <UButton type="submit" size="sm" data-testid="create-endpoint-submit">Create endpoint</UButton>
  </form>
</template>
