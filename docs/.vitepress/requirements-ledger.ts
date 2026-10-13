// The data behind the Requirements page: the ledger tools/spec_ledger.py builds from
// openspec/ (slices, main specs, open and archived changes, baseline dates), with each
// requirement's Markdown rendered to HTML here. One parser, shared with the CI check,
// instead of a second one in TypeScript. The Vite plugin below serves it as one
// /requirements.json the page fetches, so the ~0.7 MB of text ships once and loads only
// on that page.
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { createMarkdownRenderer, type SiteConfig } from "vitepress";
import type { Plugin } from "vite";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
export const LEDGER_FILE = "requirements.json";

export interface LedgerEvent {
  op: "ADDED" | "MODIFIED" | "REMOVED" | "RENAMED";
  change: string;
  date: string | null;
  archived: boolean;
}

export interface Scenario {
  name: string;
  html: string;
}

export interface LedgerRequirement {
  id: string;
  capability: string;
  code: string | null;
  group: string | null;
  slice_title: string | null;
  former_ids: string[];
  name: string;
  search: string;
  html: string;
  scenarios: Scenario[];
  status: "active" | "proposed" | "retired";
  specified: string | null;
  active_since: string | null;
  active_since_note: string | null;
  last_changed: string | null;
  open_changes: { change: string; op: string }[];
  url: string | null;
}

export interface Slice {
  capability: string;
  code: string;
  group: string;
  title: string;
  summary: string;
  description: string;
  boundary: string;
}

export interface Ledger {
  slices: Slice[];
  retired_codes: string[];
  former_codes: Record<string, string>;
  migrated_on: string;
  requirements: LedgerRequirement[];
}

interface RawRequirement extends Omit<LedgerRequirement, "html" | "scenarios" | "search"> {
  md: string;
  text: string;
  history: LedgerEvent[];
  scenarios: { name: string; md: string }[];
}

export async function buildLedger(): Promise<Ledger> {
  const raw = JSON.parse(
    execFileSync("python3", [resolve(root, "tools/spec_ledger.py")], { encoding: "utf8" }),
  ) as Omit<Ledger, "requirements"> & { requirements: RawRequirement[] };
  const config = (globalThis as { VITEPRESS_CONFIG?: SiteConfig }).VITEPRESS_CONFIG;
  const md = await createMarkdownRenderer(
    config?.srcDir ?? resolve(root, "docs"),
    config?.markdown,
    config?.site.base,
    config?.logger,
  );
  return {
    ...raw,
    requirements: raw.requirements.map(({ md: body, scenarios, history, text, ...rest }) => ({
      ...rest,
      search: `${rest.id} ${rest.former_ids.join(" ")} ${rest.name} ${text}`.toLowerCase(),
      html: md.render(body),
      scenarios: scenarios.map((s) => ({ name: s.name, html: md.render(s.md) })),
    })),
  };
}

/** Emits /requirements.json into the build and serves it from the dev server. */
export function requirementsLedgerPlugin(): Plugin {
  let ssr = false;
  return {
    name: "bundlemcp-requirements-ledger",
    configResolved(config) {
      ssr = Boolean(config.build.ssr); // VitePress also runs a server build; emit once
    },
    configureServer(server) {
      server.middlewares.use(`/${LEDGER_FILE}`, async (_req, res) => {
        res.setHeader("Content-Type", "application/json");
        res.end(JSON.stringify(await buildLedger()));
      });
    },
    async generateBundle() {
      if (ssr) return;
      this.emitFile({
        type: "asset",
        fileName: LEDGER_FILE,
        source: JSON.stringify(await buildLedger()),
      });
    },
  };
}
