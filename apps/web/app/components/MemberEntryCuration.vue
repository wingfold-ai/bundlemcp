<script setup lang="ts">
/**
 * Per-bundle curation of the prompts or resources the bundle's member upstreams list:
 * hide one from this bundle, or present it with another title or description.
 */
import type { components } from "~~/types/api";

type MemberEntryCurationRead = components["schemas"]["MemberEntryCurationRead"];
type MemberEntryKind = components["schemas"]["MemberEntryKind"];

interface EntryRow {
  enabled: boolean;
  override_title: string;
  override_description: string;
}

const props = defineProps<{ bundleName: string; kind: MemberEntryKind }>();

const api = useApi();
const errorMsg = ref("");

const isPrompt = computed(() => props.kind === "prompt");
const noun = computed(() => (isPrompt.value ? "prompts" : "resources"));

const { data: entries, error: entriesError } = useQuery<
  MemberEntryCurationRead[]
>(
  () =>
    isPrompt.value
      ? queryKeys.bundleMemberPrompts(props.bundleName)
      : queryKeys.bundleMemberResources(props.bundleName),
  async () =>
    isPrompt.value
      ? unwrap(
          await api.GET("/api/v1/bundles/{bundle}/member-prompts", {
            params: { path: { bundle: props.bundleName } },
          }),
        )
      : unwrap(
          await api.GET("/api/v1/bundles/{bundle}/member-resources", {
            params: { path: { bundle: props.bundleName } },
          }),
        ),
  { default: () => [] },
);

// A refetch lands while the admin may be editing another row — after saving one row,
// say — so a row they changed keeps their edit; the rest take the gateway's values.
const rows = useEditableRows(
  entries,
  (e) => e.entry_id,
  (e): EntryRow => ({
    enabled: e.enabled,
    override_title: e.override_title ?? "",
    override_description: e.override_description ?? "",
  }),
);

function isOverridden(e: MemberEntryCurationRead): boolean {
  return Boolean(!e.enabled || e.override_title || e.override_description);
}

async function save(entryId: string) {
  errorMsg.value = "";
  const r = rows.value[entryId];
  if (!r) return;
  // the PUT replaces the whole curation record, so every field is sent
  const body = {
    enabled: r.enabled,
    override_title: r.override_title || null,
    override_description: r.override_description || null,
  };
  const { error } = isPrompt.value
    ? await api.PUT("/api/v1/bundles/{bundle}/member-prompts/{prompt_id}", {
        params: { path: { bundle: props.bundleName, prompt_id: entryId } },
        body,
      })
    : await api.PUT("/api/v1/bundles/{bundle}/member-resources/{resource_id}", {
        params: { path: { bundle: props.bundleName, resource_id: entryId } },
        body,
      });
  if (error) {
    errorMsg.value = apiErrorMessage(error);
    return;
  }
  await invalidate(queryKeys.bundle(props.bundleName), queryKeys.catalogue);
}
</script>

<template>
  <div class="wf-card space-y-3" :data-testid="`member-${noun}`">
    <div>
      <h2 class="text-sm font-semibold">Member {{ noun }}</h2>
      <p class="wf-help">
        The {{ noun }} this bundle's member upstreams list. Disable one to hide
        it from this bundle's clients, or override how it is presented here; the
        upstream itself is unchanged.
      </p>
    </div>

    <p
      v-if="errorMsg || entriesError"
      class="text-red-600 text-sm"
      :data-testid="`member-${noun}-error`"
    >
      {{ errorMsg || entriesError?.message }}
    </p>

    <div class="overflow-x-auto">
      <table class="wf-table">
        <thead>
          <tr>
            <th>Upstream</th>
            <th>{{ isPrompt ? "Presented name" : "URI" }}</th>
            <th>Enabled</th>
            <th>Override title</th>
            <th>Override description</th>
            <th />
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="e in entries"
            :key="e.entry_id"
            :data-testid="`member-entry-${kind}-${e.key}`"
            :data-entry-id="e.entry_id"
          >
            <td>
              {{ e.server_name }}
              <UBadge
                v-if="e.stale"
                icon="i-lucide-ghost"
                color="warning"
                variant="subtle"
                :title="`The upstream no longer lists this ${kind}, so it is not served; its curation is kept in case it returns`"
                :data-testid="`member-stale-${e.entry_id}`"
                >stale</UBadge
              >
              <UBadge
                v-if="isOverridden(e)"
                icon="i-lucide-pencil"
                color="primary"
                variant="subtle"
                title="Presented differently in this bundle than the upstream reports it"
                :data-testid="`member-overridden-${e.entry_id}`"
                >overridden</UBadge
              >
            </td>
            <td class="font-mono text-xs break-all">
              {{ isPrompt ? e.presented_name : e.key }}
            </td>
            <td>
              <input
                v-if="rows[e.entry_id]"
                v-model="rows[e.entry_id]!.enabled"
                type="checkbox"
                :data-testid="`member-enabled-${e.entry_id}`"
              />
            </td>
            <td>
              <input
                v-if="rows[e.entry_id]"
                v-model="rows[e.entry_id]!.override_title"
                class="wf-input"
                :placeholder="e.title ?? ''"
                :data-testid="`member-override-title-${e.entry_id}`"
              />
            </td>
            <td>
              <textarea
                v-if="rows[e.entry_id]"
                v-model="rows[e.entry_id]!.override_description"
                class="wf-input"
                rows="2"
                :placeholder="e.description ?? ''"
                :data-testid="`member-override-description-${e.entry_id}`"
              />
            </td>
            <td>
              <UButton
                size="xs"
                variant="soft"
                :data-testid="`member-save-${e.entry_id}`"
                @click="save(e.entry_id)"
                >Save</UButton
              >
            </td>
          </tr>
          <tr v-if="entries.length === 0">
            <td
              colspan="6"
              class="text-muted"
              :data-testid="`member-${noun}-empty`"
            >
              No member {{ noun }} yet. They appear after the member upstreams'
              next discovery, if those upstreams list any.
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
