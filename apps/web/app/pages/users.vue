<script setup lang="ts">
import type { components } from "~~/types/api";

type UserRead = components["schemas"]["UserRead"];
type ConsentRead = components["schemas"]["ConsentRead"];

const api = useApi();

const users = ref<UserRead[]>([]);
const errorMsg = ref("");
const expanded = ref<Set<string>>(new Set());
const consentsByUser = ref<Record<string, ConsentRead[]>>({});

async function load() {
  const { data, error } = await api.GET("/api/v1/users", {
    params: { query: { offset: 0, limit: 100 } },
  });
  if (error) {
    errorMsg.value = apiErrorMessage(error);
    return;
  }
  users.value = data?.items ?? [];
}
await load();

async function loadConsents(userId: string) {
  const { data, error } = await api.GET("/api/v1/users/{user_id}/consents", {
    params: { path: { user_id: userId } },
  });
  if (error) {
    errorMsg.value = apiErrorMessage(error);
    return;
  }
  consentsByUser.value = { ...consentsByUser.value, [userId]: data ?? [] };
}

async function toggleConsents(userId: string) {
  errorMsg.value = "";
  const next = new Set(expanded.value);
  if (next.has(userId)) {
    next.delete(userId);
  } else {
    next.add(userId);
    await loadConsents(userId);
  }
  expanded.value = next;
}

async function deactivateUser(userId: string) {
  errorMsg.value = "";
  const { error } = await api.POST("/api/v1/users/{user_id}:deactivate", {
    params: { path: { user_id: userId } },
  });
  if (error) {
    errorMsg.value = apiErrorMessage(error);
    return;
  }
  await load();
}

async function revokeConsent(userId: string, consentId: string) {
  errorMsg.value = "";
  const { error } = await api.DELETE("/api/v1/users/{user_id}/consents/{consent_id}", {
    params: { path: { user_id: userId, consent_id: consentId } },
  });
  if (error) {
    errorMsg.value = apiErrorMessage(error);
    return;
  }
  await loadConsents(userId);
}
</script>

<template>
  <div class="space-y-6">
    <h1 class="text-lg font-semibold">Users</h1>

    <p v-if="errorMsg" class="text-red-600 text-sm" data-testid="error">{{ errorMsg }}</p>

    <div class="overflow-x-auto">
      <table class="wf-table" data-testid="users-table">
        <thead>
          <tr>
            <th>Email</th>
            <th>Display name</th>
            <th>Admin</th>
            <th>Active</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="u in users" :key="u.id">
            <tr :data-testid="`user-${u.email}`">
              <td>{{ u.email }}</td>
              <td>{{ u.display_name }}</td>
              <td>
                <UBadge :color="u.is_admin ? 'primary' : 'neutral'" variant="subtle">
                  {{ u.is_admin ? "admin" : "user" }}
                </UBadge>
              </td>
              <td>
                <UBadge :color="u.is_active ? 'success' : 'neutral'" variant="subtle">
                  {{ u.is_active ? "active" : "inactive" }}
                </UBadge>
              </td>
              <td class="space-x-2">
                <UButton
                  size="xs"
                  variant="outline"
                  :data-testid="`consents-${u.email}`"
                  @click="toggleConsents(u.id)"
                >
                  {{ expanded.has(u.id) ? "Hide consents" : "Consents" }}
                </UButton>
                <UButton
                  size="xs"
                  color="error"
                  variant="outline"
                  :data-testid="`deactivate-user-${u.email}`"
                  :disabled="!u.is_active"
                  @click="deactivateUser(u.id)"
                >
                  Deactivate
                </UButton>
              </td>
            </tr>
            <tr v-if="expanded.has(u.id)">
              <td colspan="5">
                <p
                  v-if="(consentsByUser[u.id] ?? []).length === 0"
                  class="text-sm text-muted"
                >
                  No consents.
                </p>
                <table v-else class="wf-table">
                  <thead>
                    <tr>
                      <th>Client</th>
                      <th>Endpoint</th>
                      <th>Granted at</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="c in consentsByUser[u.id]" :key="c.id">
                      <td>{{ c.client_id }}</td>
                      <td>{{ c.endpoint_id }}</td>
                      <td><TimestampText :value="c.granted_at" /></td>
                      <td>
                        <UButton
                          size="xs"
                          color="error"
                          variant="outline"
                          :data-testid="`revoke-consent-${c.id}`"
                          @click="revokeConsent(u.id, c.id)"
                        >
                          Revoke
                        </UButton>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>
  </div>
</template>
