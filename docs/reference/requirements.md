---
title: Requirements
description: "Every bundlemcp requirement by slice, with its status and the dates it was specified, became active and
  last changed."
aside: false
---

<script setup>
import RequirementsTable from "../.vitepress/theme/RequirementsTable.vue";
</script>

# Requirements

bundlemcp's behaviour is specified as requirements, each with a stable code such as `BND-5`. The prefix names the
**slice** the requirement belongs to: `BND` is bundles, `UPS` upstream servers, `SES` sessions. There are 13
slices, each one area of the gateway.
Tests cite these codes in their names, so a code here leads to the tests that verify it.

- **Active** requirements describe what the gateway does today.
- **Proposed** ones are specified but not built yet; each links the change that would build it.

Pick a slice card to read what that area covers and every requirement in it, or search across all of them. Each
requirement is shown in full, with the scenarios that make it testable. The page address keeps the filter, so
`?slice=BND` links to the bundle requirements and `#BND-5` to one requirement.

The dates come from the repository, not from anyone's memory. *Specified* is when the requirement was first written
down. *Active since* is when it was first implemented: the day the change that added it was archived, or, for
requirements older than the move to OpenSpec on 2026-10-13, the first commit that tested or cited it in code. *Last
changed* is the last archived change that modified it. Codes published before the slices were consolidated on
2026-10-13 (`DISC-3`, `OAS-10`, …) are shown as "was" under the current code, and searching for one finds it.

The specifications themselves are in [openspec/](https://github.com/wingfold-ai/bundlemcp/tree/main/openspec) in the
repository.

<ClientOnly>
  <RequirementsTable />
</ClientOnly>
