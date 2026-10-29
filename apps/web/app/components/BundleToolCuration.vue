<script setup lang="ts">
/** How a bundle presents each member tool: enabled, renamed, retitled, re-described, re-annotated. */
import type { components } from "~~/types/api";

type BundleToolRead = components["schemas"]["BundleToolRead"];

interface CurationRow {
  enabled: boolean;
  override_name: string;
  override_title: string;
  override_description: string;
  // edited as JSON text, parsed and checked before it is saved
  override_annotations: string;
}

const props = defineProps<{ bundleName: string; tools: BundleToolRead[] }>();

const api = useApi();

const curation = useEditableRows(
  toRef(props, "tools"),
  (t) => t.tool_id,
  (t): CurationRow => ({
    enabled: t.enabled,
    override_name: t.override_name ?? "",
    override_title: t.override_title ?? "",
    override_description: t.override_description ?? "",
    override_annotations: t.override_annotations ? JSON.stringify(t.override_annotations) : "",
  }),
);

function isOverridden(t: BundleToolRead): boolean {
  return Boolean(
    t.override_name || t.override_title || t.override_description || t.override_annotations,
  );
}

function parsedAnnotations(text: string): Record<string, unknown> | null {
  if (!text.trim()) return null;
  let annotations: unknown = null;
  try {
    annotations = JSON.parse(text);
  } catch {
    // reported below, as any other value that is not an object
  }
  if (annotations === null || typeof annotations !== "object" || Array.isArray(annotations)) {
    throw new ValidationProblem(
      'Override annotations must be a JSON object, e.g. {"readOnlyHint": true}',
    );
  }
  return annotations as Record<string, unknown>;
}

const { run: saveCuration, error } = useAction(
  async (toolId: string) => {
    const c = curation.value[toolId];
    if (!c) return;
    const annotations = parsedAnnotations(c.override_annotations);
    // the PUT replaces the whole curation record, so every override is sent, not just the
    // ones this row edits; a duplicate presented name answers 409, shown as the error
    return await api.PUT("/api/v1/bundles/{name}/tools/{tool_id}", {
      params: { path: { name: props.bundleName, tool_id: toolId } },
      body: {
        enabled: c.enabled,
        override_name: c.override_name || null,
        override_title: c.override_title || null,
        override_description: c.override_description || null,
        override_annotations: annotations,
      },
    });
  },
  { invalidates: () => [queryKeys.bundle(props.bundleName), queryKeys.catalogue] },
);
</script>

<template>
  <div class="wf-card space-y-3" data-testid="card-curation">
    <h2 class="text-sm font-semibold">Tool curation</h2>
    <p v-if="error" class="text-red-600 text-sm" data-testid="error">{{ error }}</p>
    <div class="overflow-x-auto">
      <table class="wf-table" data-testid="curation-table">
        <thead>
          <tr>
            <th>Upstream</th>
            <th>Upstream name</th>
            <th>Presented name</th>
            <th>Enabled</th>
            <th>Override name</th>
            <th>Override title</th>
            <th>Override description</th>
            <th>Override annotations</th>
            <th />
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="t in tools"
            :key="t.tool_id"
            :data-testid="`curation-${t.server_name}__${t.name}`"
            :data-tool-id="t.tool_id"
          >
            <td>
              {{ t.server_name }}
              <UBadge
                v-if="!t.member_enabled"
                icon="i-lucide-eye-off"
                color="neutral"
                variant="subtle"
                >member disabled</UBadge
              >
              <UBadge
                v-if="t.stale"
                icon="i-lucide-ghost"
                color="warning"
                variant="subtle"
                title="The upstream no longer lists this tool, so it is not served; its curation is kept in case it returns"
                :data-testid="`stale-${t.tool_id}`"
                >stale</UBadge
              >
              <UBadge
                v-if="t.member_enabled && isOverridden(t)"
                icon="i-lucide-pencil"
                color="primary"
                variant="subtle"
                title="Presented differently in this bundle than the upstream reports it"
                :data-testid="`overridden-${t.tool_id}`"
                >overridden</UBadge
              >
            </td>
            <td>{{ t.name }}</td>
            <td :data-testid="`presented-${t.tool_id}`">{{ t.presented_name }}</td>
            <td>
              <input
                v-if="curation[t.tool_id]"
                v-model="curation[t.tool_id]!.enabled"
                type="checkbox"
                :data-testid="`curation-toggle-${t.tool_id}`"
              />
            </td>
            <td>
              <input
                v-if="curation[t.tool_id]"
                v-model="curation[t.tool_id]!.override_name"
                class="wf-input"
                :data-testid="`override-name-${t.tool_id}`"
              />
            </td>
            <td>
              <input
                v-if="curation[t.tool_id]"
                v-model="curation[t.tool_id]!.override_title"
                class="wf-input"
                :data-testid="`override-title-${t.tool_id}`"
              />
            </td>
            <td>
              <textarea
                v-if="curation[t.tool_id]"
                v-model="curation[t.tool_id]!.override_description"
                class="wf-input"
                rows="2"
                :placeholder="t.description ?? ''"
                :data-testid="`override-description-${t.tool_id}`"
              />
            </td>
            <td>
              <textarea
                v-if="curation[t.tool_id]"
                v-model="curation[t.tool_id]!.override_annotations"
                class="wf-input font-mono text-xs"
                rows="2"
                placeholder='{"readOnlyHint": true}'
                :data-testid="`override-annotations-${t.tool_id}`"
              />
            </td>
            <td>
              <UButton
                size="xs"
                variant="soft"
                :data-testid="`curation-save-${t.tool_id}`"
                @click="saveCuration(t.tool_id)"
                >Save</UButton
              >
            </td>
          </tr>
          <tr v-if="tools.length === 0">
            <td colspan="9" class="text-muted">No tools in this bundle.</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
