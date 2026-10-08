<script setup lang="ts">
import type { components } from "~~/types/api";

type AuditStatus = components["schemas"]["AuditStatus"];
type AuditRecordRead = components["schemas"]["AuditRecordRead"];

const api = useApi();

const records = ref<AuditRecordRead[]>([]);
const errorMsg = ref("");

const filterEndpoint = ref("");
const filterStatus = ref<AuditStatus | "any">("any");
const filterTool = ref("");
const filterFrom = ref("");
const filterTo = ref("");

function buildQuery() {
  const query: {
    offset: number;
    limit: number;
    endpoint_name?: string;
    status?: AuditStatus;
    tool_name?: string;
    created_from?: string;
    created_to?: string;
  } = { offset: 0, limit: 100 };
  if (filterEndpoint.value.trim()) query.endpoint_name = filterEndpoint.value.trim();
  if (filterStatus.value !== "any") query.status = filterStatus.value;
  if (filterTool.value.trim()) query.tool_name = filterTool.value.trim();
  if (filterFrom.value) query.created_from = new Date(filterFrom.value).toISOString();
  if (filterTo.value) query.created_to = new Date(filterTo.value).toISOString();
  return query;
}

async function load() {
  errorMsg.value = "";
  const { data, error } = await api.GET("/api/v1/audit-records", {
    params: { query: buildQuery() },
  });
  if (error) {
    errorMsg.value = apiErrorMessage(error);
    return;
  }
  records.value = data?.items ?? [];
}
await load();

function statusColor(status: string): "success" | "error" | "warning" | "neutral" {
  if (status === "success") return "success";
  if (status === "error") return "error";
  if (status === "denied") return "warning";
  return "neutral";
}

function csvCell(v: unknown): string {
  const s = v == null ? "" : String(v);
  return /[",\n]/.test(s) ? `"${s.replaceAll('"', '""')}"` : s;
}

function exportCsv() {
  const header = [
    "created_at",
    "endpoint_name",
    "bundle_name",
    "server_name",
    "presented_tool_name",
    "status",
    "duration_ms",
    "denied_reason",
    "error_message",
  ];
  const lines = [
    header.join(","),
    ...records.value.map((r) =>
      [
        r.created_at,
        r.endpoint_name,
        r.bundle_name,
        r.server_name,
        r.presented_tool_name,
        r.status,
        r.duration_ms,
        r.denied_reason,
        r.error_message,
      ]
        .map(csvCell)
        .join(","),
    ),
  ];
  const blob = new Blob([lines.join("\n")], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "audit-records.csv";
  a.click();
  URL.revokeObjectURL(url);
}
</script>

<template>
  <div class="space-y-6">
    <h1 class="text-lg font-semibold">Audit</h1>

    <p v-if="errorMsg" class="text-red-600 text-sm" data-testid="error">{{ errorMsg }}</p>

    <div class="wf-card">
      <div class="grid grid-cols-3 gap-3">
        <div>
          <label class="wf-label">Endpoint</label>
          <input v-model="filterEndpoint" class="wf-input" data-testid="filter-endpoint" />
        </div>
        <div>
          <label class="wf-label">Status</label>
          <select v-model="filterStatus" class="wf-input" data-testid="filter-status">
            <option value="any">any</option>
            <option value="success">success</option>
            <option value="error">error</option>
            <option value="denied">denied</option>
          </select>
        </div>
        <div>
          <label class="wf-label">Tool</label>
          <input v-model="filterTool" class="wf-input" data-testid="filter-tool" />
        </div>
        <div>
          <label class="wf-label">From</label>
          <input
            v-model="filterFrom"
            type="datetime-local"
            class="wf-input"
            data-testid="filter-from"
          />
        </div>
        <div>
          <label class="wf-label">To</label>
          <input v-model="filterTo" type="datetime-local" class="wf-input" data-testid="filter-to" />
        </div>
        <div class="flex items-end gap-2">
          <UButton data-testid="filter-apply" @click="load">Apply</UButton>
          <UButton variant="outline" data-testid="export-csv" @click="exportCsv">
            Export CSV
          </UButton>
        </div>
      </div>
    </div>

    <div class="overflow-x-auto">
      <table class="wf-table" data-testid="audit-table">
        <thead>
          <tr>
            <th>Created at</th>
            <th>Endpoint</th>
            <th>Bundle</th>
            <th>Server</th>
            <th>Tool (presented)</th>
            <th>Status</th>
            <th>Duration (ms)</th>
            <th>Reason / error</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(r, index) in records" :key="r.id" :data-testid="`audit-row-${index}`">
            <td><TimestampText :value="r.created_at" /></td>
            <td class="whitespace-nowrap">{{ r.endpoint_name }}</td>
            <td class="whitespace-nowrap">{{ r.bundle_name }}</td>
            <td class="whitespace-nowrap">{{ r.server_name }}</td>
            <td class="break-all">{{ r.presented_tool_name }}</td>
            <td>
              <UBadge :color="statusColor(r.status)" variant="subtle">{{ r.status }}</UBadge>
            </td>
            <td class="tabular-nums">{{ r.duration_ms }}</td>
            <td>{{ r.denied_reason ?? r.error_message }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
