<script setup lang="ts">
import type { components } from "~~/types/api";

type AuditStatus = components["schemas"]["AuditStatus"];
type AuditRecordRead = components["schemas"]["AuditRecordRead"];
type ApiKeyRead = components["schemas"]["ApiKeyRead"];

const api = useApi();

const records = ref<AuditRecordRead[]>([]);
const total = ref(0);
const apiKeys = ref<ApiKeyRead[]>([]);
const errorMsg = ref("");

const filterEndpoint = ref("");
const filterBundle = ref("");
const filterServer = ref("");
const filterStatus = ref<AuditStatus | "any">("any");
const filterTool = ref("");
const filterApiKey = ref("");
const filterUser = ref("");
const filterFrom = ref("");
const filterTo = ref("");

type AuditQuery = {
  endpoint_name?: string;
  bundle_name?: string;
  server_name?: string;
  status?: AuditStatus;
  tool_name?: string;
  api_key_id?: string;
  user_id?: string;
  created_from?: string;
  created_to?: string;
};

/** The current filters, shared by the list and the export. */
function filters(): AuditQuery {
  const query: AuditQuery = {};
  const text = (value: string) => value.trim() || undefined;
  query.endpoint_name = text(filterEndpoint.value);
  query.bundle_name = text(filterBundle.value);
  query.server_name = text(filterServer.value);
  query.tool_name = text(filterTool.value);
  query.api_key_id = text(filterApiKey.value);
  query.user_id = text(filterUser.value);
  if (filterStatus.value !== "any") query.status = filterStatus.value;
  if (filterFrom.value) query.created_from = new Date(filterFrom.value).toISOString();
  if (filterTo.value) query.created_to = new Date(filterTo.value).toISOString();
  return Object.fromEntries(Object.entries(query).filter(([, value]) => value !== undefined));
}

async function load() {
  errorMsg.value = "";
  const { data, error } = await api.GET("/api/v1/audit-records", {
    params: { query: { offset: 0, limit: 100, ...filters() } },
  });
  if (error) {
    errorMsg.value = apiErrorMessage(error);
    return;
  }
  records.value = data?.items ?? [];
  total.value = data?.total ?? 0;
}

async function loadKeys() {
  const { data } = await api.GET("/api/v1/api-keys", { params: { query: { limit: 500 } } });
  apiKeys.value = data?.items ?? [];
}

await Promise.all([load(), loadKeys()]);

function statusColor(status: string): "success" | "error" | "warning" | "neutral" {
  if (status === "success") return "success";
  if (status === "error") return "error";
  if (status === "denied") return "warning";
  return "neutral";
}

/** Download the whole filtered result from the gateway, not only the rows shown. */
function exportCsv() {
  const query = new URLSearchParams(filters() as Record<string, string>);
  window.location.assign(`${apiBase()}/api/v1/audit-records:export?${query}`);
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
          <label class="wf-label">Bundle</label>
          <input v-model="filterBundle" class="wf-input" data-testid="filter-bundle" />
        </div>
        <div>
          <label class="wf-label">Upstream</label>
          <input v-model="filterServer" class="wf-input" data-testid="filter-server" />
        </div>
        <div>
          <label class="wf-label">Tool</label>
          <input v-model="filterTool" class="wf-input" data-testid="filter-tool" />
        </div>
        <div>
          <label class="wf-label">Status</label>
          <select v-model="filterStatus" class="wf-input" data-testid="filter-status">
            <option value="any">any</option>
            <option value="success">success</option>
            <option value="error">error</option>
            <option value="denied">denied</option>
            <option value="input_required">input_required</option>
          </select>
        </div>
        <div>
          <label class="wf-label">API key</label>
          <select v-model="filterApiKey" class="wf-input" data-testid="filter-api-key">
            <option value="">any</option>
            <option v-for="key in apiKeys" :key="key.id" :value="key.id">
              {{ key.name }} ({{ key.key_prefix }})
            </option>
          </select>
        </div>
        <div>
          <label class="wf-label">User id</label>
          <input v-model="filterUser" class="wf-input" data-testid="filter-user" />
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

    <p class="text-sm text-gray-500" data-testid="audit-total">
      Showing {{ records.length }} of {{ total }} matching records; Export CSV downloads all of them.
    </p>

    <div class="overflow-x-auto">
      <table class="wf-table" data-testid="audit-table">
        <thead>
          <tr>
            <th>Created at</th>
            <th>Endpoint</th>
            <th>Bundle</th>
            <th>Upstream</th>
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
