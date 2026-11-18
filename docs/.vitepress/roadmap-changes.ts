// The roadmap's "In progress" station: one entry per change in openspec/changes/ that
// is not archived yet, read when the site is built. The page imports it as
// virtual:roadmap-changes, so the few lines land in its HTML and need no fetch.
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { dirname, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";
import type { Plugin } from "vite";
import { repositoryPublic, repositoryUrl } from "./repository-links";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const changesDir = resolve(root, "openspec/changes");
const MODULE_ID = "virtual:roadmap-changes";
const RESOLVED_ID = `\0${MODULE_ID}`;

export interface RoadmapChange {
  name: string;
  why: string;
  done: number;
  total: number;
  url: string | null;
}

/** Markdown inline syntax reduced to its text: links keep their label, code its content. */
function plainText(markdown: string): string {
  return markdown
    .replace(/!?\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/`([^`]*)`/g, "$1")
    .replace(/(\*\*|__|\*|_)(\S[^*_]*?)\1/g, "$2")
    .replace(/\s+/g, " ")
    .trim();
}

/** The first sentence of the first paragraph under "## Why". */
function firstSentenceOfWhy(proposal: string): string {
  const lines = proposal.split("\n");
  const start = lines.findIndex((line) => /^##\s+Why\s*$/.test(line));
  if (start === -1) return "";
  const paragraph: string[] = [];
  for (const line of lines.slice(start + 1)) {
    if (line.startsWith("#")) break;
    if (line.trim() === "" || line.trim().startsWith("<!--")) {
      if (paragraph.length) break;
      continue;
    }
    paragraph.push(line);
  }
  const text = plainText(paragraph.join(" "));
  const end = text.search(/[.!?](\s|$)/);
  return end === -1 ? text : text.slice(0, end + 1);
}

/** Checked and all task checkboxes; only a box holding nothing but x counts as done. */
function countTasks(tasks: string): { done: number; total: number } {
  let done = 0;
  let total = 0;
  for (const match of tasks.matchAll(/^\s*[-*]\s+\[([^\]]*)\]/gm)) {
    total += 1;
    if (match[1].trim().toLowerCase() === "x") done += 1;
  }
  return { done, total };
}

function read(path: string): string {
  return existsSync(path) ? readFileSync(path, "utf8") : "";
}

export function readRoadmapChanges(): RoadmapChange[] {
  if (!existsSync(changesDir)) return [];
  return readdirSync(changesDir, { withFileTypes: true })
    .filter((entry) => entry.isDirectory() && entry.name !== "archive")
    .map((entry) => entry.name)
    .sort()
    .map((name) => ({
      name,
      why: firstSentenceOfWhy(read(resolve(changesDir, name, "proposal.md"))),
      ...countTasks(read(resolve(changesDir, name, "tasks.md"))),
      url: repositoryPublic
        ? `${repositoryUrl}/blob/main/openspec/changes/${name}/proposal.md`
        : null,
    }));
}

/** Provides virtual:roadmap-changes, rebuilt in the dev server whenever a change moves. */
export function roadmapChangesPlugin(): Plugin {
  return {
    name: "bundlemcp-roadmap-changes",
    resolveId(id) {
      return id === MODULE_ID ? RESOLVED_ID : undefined;
    },
    load(id) {
      if (id !== RESOLVED_ID) return undefined;
      return `export default ${JSON.stringify(readRoadmapChanges())};`;
    },
    configureServer(server) {
      server.watcher.add(changesDir);
      const refresh = (path: string) => {
        if (!path.startsWith(changesDir + sep)) return;
        const module = server.moduleGraph.getModuleById(RESOLVED_ID);
        if (!module) return;
        server.moduleGraph.invalidateModule(module);
        server.ws.send({ type: "full-reload" });
      };
      server.watcher.on("add", refresh);
      server.watcher.on("addDir", refresh);
      server.watcher.on("change", refresh);
      server.watcher.on("unlink", refresh);
      server.watcher.on("unlinkDir", refresh);
    },
  };
}
