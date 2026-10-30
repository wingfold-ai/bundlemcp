<script setup lang="ts">
import type { components } from "~~/types/api";

type BundleRead = components["schemas"]["BundleRead"];
type BundleMemberRead = components["schemas"]["BundleMemberRead"];
type BundleToolRead = components["schemas"]["BundleToolRead"];

const api = useApi();
const route = useRoute();
const bundleName = computed(() => String(route.params.name));

const [
  { data: bundle, error: bundleError },
  { data: members, error: membersError },
  { data: tools, error: toolsError },
  { data: profiles },
  { data: allServers, error: serversError },
  { data: endpoints, error: endpointsError },
  { data: allBundles },
] = await Promise.all([
  useQuery<BundleRead | null>(
    () => queryKeys.bundle(bundleName.value),
    async () =>
      unwrap(
        await api.GET("/api/v1/bundles/{name}", {
          params: { path: { name: bundleName.value } },
        }),
      ),
    { default: () => null },
  ),
  useQuery<BundleMemberRead[]>(
    () => queryKeys.bundleMembers(bundleName.value),
    async () =>
      unwrap(
        await api.GET("/api/v1/bundles/{name}/upstreams", {
          params: { path: { name: bundleName.value } },
        }),
      ),
    { default: () => [] },
  ),
  useQuery<BundleToolRead[]>(
    () => queryKeys.bundleTools(bundleName.value),
    async () =>
      unwrap(
        await api.GET("/api/v1/bundles/{name}/tools", {
          params: { path: { name: bundleName.value } },
        }),
      ),
    { default: () => [] },
  ),
  useProfiles(),
  useUpstreams(),
  useEndpoints(),
  // read for the rename card, so a taken name is seen before anything is sent
  useBundles(),
]);

// a missing bundle shows "not found" instead of the errors its sub-resources answer with
const notFound = computed(() => bundleError.value?.status === 404);
// what the page failed to load; a failed action shows on the card that ran it
const loadError = computed(() =>
  notFound.value
    ? ""
    : (bundleError.value ??
        membersError.value ??
        toolsError.value ??
        serversError.value ??
        endpointsError.value)?.message ?? "",
);

// the names a rename would collide with: every bundle but this one
const otherBundleNames = computed(() =>
  allBundles.value.map((b) => b.name).filter((n) => n !== bundleName.value),
);

async function renamed(oldName: string, newName: string) {
  // endpoints follow the bundle by id, but their pages show the bundle's name
  await invalidate(
    queryKeys.bundles,
    queryKeys.bundle(oldName),
    queryKeys.composition,
    queryKeys.endpoints,
    queryKeys.catalogue,
  );
  await navigateTo(`/bundles/${newName}`);
}
</script>

<template>
  <div class="space-y-6">
    <h1 class="text-lg font-semibold">Bundle: {{ bundleName }}</h1>

    <p v-if="loadError" class="text-red-600 text-sm" data-testid="error">{{ loadError }}</p>

    <p v-if="notFound" class="text-muted" data-testid="not-found">not found</p>

    <template v-else-if="bundle">
      <!-- keyed, so another bundle always starts from its own values -->
      <BundleMetaCard :key="bundle.id" :bundle="bundle" />

      <div class="wf-card max-w-xl" data-testid="card-rename">
        <RenameCard
          kind="bundle"
          :current="bundleName"
          :taken="otherBundleNames"
          heading="Rename bundle"
          acknowledgement="I understand that automation naming the old bundle would create a new one"
          require-acknowledgement
          test-id-prefix="bundle-rename"
          @renamed="(newName) => renamed(bundleName, newName)"
        >
          <template #consequence="{ newName }">
            <div class="space-y-2" data-testid="bundle-rename-warning">
              <p>
                Members, curation, prompts, resources and endpoints stay with the bundle, and its
                endpoint URLs do not change.
              </p>
              <p class="text-red-600">
                A bootstrap file or an exported document that still names
                <code>{{ bundleName }}</code> creates a new, empty bundle under that name the next
                time it is applied. Update them to <code>{{ newName }}</code> as well.
              </p>
            </div>
          </template>
        </RenameCard>
      </div>

      <BundleMembersCard :bundle-name="bundleName" :members="members" :upstreams="allServers" />
      <BundleToolCuration :bundle-name="bundleName" :tools="tools" />

      <!-- The bundle's own context -->
      <BundlePrompts :bundle-name="bundleName" />
      <BundleResources :bundle-name="bundleName" />

      <!-- What the member upstreams list, curated for this bundle -->
      <MemberEntryCuration :bundle-name="bundleName" kind="prompt" />
      <MemberEntryCuration :bundle-name="bundleName" kind="resource" />

      <BundleEndpointsCard :bundle="bundle" :endpoints="endpoints" :profiles="profiles" />
    </template>
  </div>
</template>
