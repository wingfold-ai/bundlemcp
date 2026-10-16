<script setup lang="ts">
import type { components } from "~~/types/api";

type BundleMemberRead = components["schemas"]["BundleMemberRead"];

// The composition overview: which bundle contains which server, as one
// grid. The per-bundle membership pages answer "what is in this bundle"; this
// answers the questions that span bundles — what a server is used by, and what
// is registered but in no bundle at all.
const { data: bundleList, error: bundlesError } = await useBundles();
const { data: serverList, error: serversError } = await useUpstreams();
const { data: members, error: membersError } = await useComposition();
const loadError = computed(() => bundlesError.value ?? serversError.value ?? membersError.value);

const bundles = computed(() => bundleList.value);
const servers = computed(() => serverList.value);

function membership(bundleName: string, serverName: string): BundleMemberRead | undefined {
  return members.value[bundleName]?.[serverName];
}

/** How many bundles a server belongs to; zero means it is registered but unused. */
function bundleCount(serverName: string): number {
  return bundles.value.filter((b) => membership(b.name, serverName)).length;
}

function serverCount(bundleName: string): number {
  return Object.keys(members.value[bundleName] ?? {}).length;
}

const orphans = computed(() => servers.value.filter((s) => bundleCount(s.name) === 0));
</script>

<template>
  <div class="space-y-6">
    <div>
      <NuxtLink
        to="/bundles"
        class="inline-flex items-center gap-1.5 text-sm text-muted hover:text-default mb-2"
        data-testid="back-to-bundles"
      >
        <UIcon name="i-lucide-arrow-left" class="size-4" />All bundles
      </NuxtLink>
      <h1 class="text-lg font-semibold">Composition</h1>
    </div>

    <p v-if="loadError" class="text-red-600 text-sm" data-testid="error">
      {{ loadError.message }}
    </p>

    <div v-if="bundles.length === 0 || servers.length === 0" class="wf-card text-sm text-muted"
      data-testid="matrix-empty">
      Nothing to compose yet: register an upstream and create a bundle first.
    </div>

    <div v-else class="overflow-x-auto">
      <table class="wf-table" data-testid="matrix-table">
        <thead>
          <tr>
            <th class="sticky left-0 bg-muted">Bundle</th>
            <th v-for="s in servers" :key="s.name" class="text-center">
              <NuxtLink :to="`/upstreams/${s.name}`" class="underline whitespace-nowrap">{{
                s.name
              }}</NuxtLink>
            </th>
            <th class="text-center whitespace-nowrap">Upstream servers</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="b in bundles" :key="b.name" :data-testid="`matrix-row-${b.name}`">
            <td class="sticky left-0 bg-muted whitespace-nowrap">
              <NuxtLink :to="`/bundles/${b.name}`" class="underline">{{ b.name }}</NuxtLink>
            </td>
            <td v-for="s in servers" :key="s.name" class="text-center"
              :data-testid="`matrix-${b.name}-${s.name}`">
              <UIcon v-if="membership(b.name, s.name)?.enabled" name="i-lucide-check"
                class="size-4 text-primary" :aria-label="`${s.name} is in ${b.name}`"
                :title="`${s.name} is in ${b.name}`" />
              <UIcon v-else-if="membership(b.name, s.name)" name="i-lucide-pause"
                class="size-4 text-muted" :aria-label="`${s.name} is in ${b.name} but disabled`"
                :title="`${s.name} is in ${b.name} but disabled, so its tools are not served`" />
              <span v-else class="text-muted" aria-hidden="true">·</span>
            </td>
            <td class="text-center text-muted" :data-testid="`matrix-count-${b.name}`">
              {{ serverCount(b.name) }}
            </td>
          </tr>
          <tr class="text-muted">
            <td class="sticky left-0 bg-muted">Bundles</td>
            <td v-for="s in servers" :key="s.name" class="text-center"
              :data-testid="`matrix-total-${s.name}`">
              {{ bundleCount(s.name) }}
            </td>
            <td />
          </tr>
        </tbody>
      </table>
    </div>

    <p class="wf-help">
      A check means the upstream is a member of that bundle and its tools are served. A pause icon
      means it is a member but disabled, so the bundle keeps the membership without serving its
      tools. The last row counts the bundles each upstream appears in.
      <template v-if="orphans.length">
        <strong>{{ orphans.map((s) => s.name).join(", ") }}</strong>
        {{ orphans.length === 1 ? "is" : "are" }} registered but in no bundle, so
        {{ orphans.length === 1 ? "it is" : "they are" }} not reachable through any endpoint.
      </template>
    </p>
  </div>
</template>
