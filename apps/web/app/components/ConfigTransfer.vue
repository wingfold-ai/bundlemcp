<script setup lang="ts">
/**
 * Export and import of the whole configuration (the management spec's export
 * document). An import is always previewed as a dry run first, and written only
 * once the admin confirms that report.
 */
import type { components } from "~~/types/api";

type ImportReport = components["schemas"]["ImportReport"];
type BootstrapDocument = components["schemas"]["BootstrapDocument"];

const api = useApi();
const errorMsg = ref("");
const includeSecrets = ref(false);
const exporting = ref(false);

const pending = ref<BootstrapDocument | null>(null);
const preview = ref<ImportReport | null>(null);
const applied = ref<ImportReport | null>(null);
const importing = ref(false);

async function exportConfig() {
  errorMsg.value = "";
  exporting.value = true;
  try {
    const { data, error } = await api.GET("/api/v1/export", {
      params: { query: { include_secrets: includeSecrets.value } },
    });
    if (error) {
      errorMsg.value = apiErrorMessage(error);
      return;
    }
    const blob = new Blob([JSON.stringify(data, null, 2) + "\n"], { type: "application/json" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = includeSecrets.value
      ? "bundlemcp-export-with-secrets.json"
      : "bundlemcp-export.json";
    link.click();
    URL.revokeObjectURL(link.href);
  } finally {
    exporting.value = false;
  }
}

/** Read the chosen file and show what importing it would do, writing nothing. */
async function chooseFile(event: Event) {
  errorMsg.value = "";
  preview.value = null;
  applied.value = null;
  const file = (event.target as HTMLInputElement).files?.[0];
  if (!file) return;
  let doc: BootstrapDocument;
  try {
    doc = JSON.parse(await file.text());
  } catch {
    errorMsg.value = `${file.name} is not a JSON document`;
    return;
  }
  pending.value = doc;
  preview.value = await post(doc, true);
}

async function post(doc: BootstrapDocument, dryRun: boolean): Promise<ImportReport | null> {
  importing.value = true;
  try {
    const { data, error } = await api.POST("/api/v1/import", {
      params: { query: { dry_run: dryRun } },
      body: doc,
    });
    if (error) {
      errorMsg.value = apiErrorMessage(error);
      return null;
    }
    return data;
  } finally {
    importing.value = false;
  }
}

const previewHasErrors = computed(() =>
  (preview.value?.results ?? []).some((r) => r.outcome === "error"),
);

async function confirmImport() {
  if (!pending.value) return;
  applied.value = await post(pending.value, false);
  if (applied.value?.applied) {
    preview.value = null;
    pending.value = null;
    await invalidate(
      queryKeys.upstreams,
      queryKeys.bundles,
      queryKeys.composition,
      queryKeys.endpoints,
      queryKeys.catalogue,
    );
  }
}

function cancelImport() {
  pending.value = null;
  preview.value = null;
}
</script>

<template>
  <div class="wf-card space-y-4" data-testid="config-transfer">
    <h2 class="text-sm font-semibold">Export and import</h2>
    <p class="text-sm text-muted">
      The export is the whole configuration — upstreams, bundles with their curation, prompts and
      resources, endpoints — as a document bootstrap and import both accept. Secrets are written as
      placeholders that keep what the target stores.
    </p>

    <p v-if="errorMsg" class="text-red-600 text-sm" data-testid="transfer-error">{{ errorMsg }}</p>

    <div class="flex flex-wrap items-center gap-3">
      <UButton
        size="sm"
        variant="outline"
        :loading="exporting"
        data-testid="export-config"
        @click="exportConfig"
        >Export</UButton
      >
      <label class="text-sm inline-flex items-center gap-2">
        <input v-model="includeSecrets" type="checkbox" data-testid="export-include-secrets" />
        include secret values — the file is then a credential, and the export is audited
      </label>
    </div>

    <div class="space-y-2">
      <label class="wf-label" for="import-file">Import a document</label>
      <input
        id="import-file"
        type="file"
        accept="application/json,.json"
        data-testid="import-file"
        @change="chooseFile"
      />
    </div>

    <div v-if="preview" class="space-y-2" data-testid="import-preview">
      <p class="text-sm">
        Dry run — nothing has been written. Importing never deletes what the document leaves out.
      </p>
      <table class="wf-table">
        <thead>
          <tr>
            <th>Kind</th>
            <th>Name</th>
            <th>Outcome</th>
            <th>Note</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="r in preview.results"
            :key="`${r.kind}-${r.name}`"
            :data-testid="`import-result-${r.kind}-${r.name}`"
          >
            <td>{{ r.kind }}</td>
            <td><code>{{ r.name }}</code></td>
            <td>
              <UBadge
                :color="r.outcome === 'error' ? 'error' : r.outcome === 'skipped' ? 'neutral' : 'primary'"
                variant="subtle"
                >{{ r.outcome }}</UBadge
              >
            </td>
            <td class="text-muted">{{ r.message }}</td>
          </tr>
        </tbody>
      </table>
      <p v-if="previewHasErrors" class="text-red-600 text-sm">
        The document cannot be imported while any resource errors; nothing would be written.
      </p>
      <div class="flex gap-2">
        <UButton
          size="sm"
          :disabled="previewHasErrors"
          :loading="importing"
          data-testid="import-confirm"
          @click="confirmImport"
          >Apply import</UButton
        >
        <UButton size="sm" color="neutral" variant="outline" @click="cancelImport">Cancel</UButton>
      </div>
    </div>

    <p v-if="applied?.applied" class="text-sm" data-testid="import-applied">
      Imported: {{ applied.results.length }} resources.
    </p>
  </div>
</template>
