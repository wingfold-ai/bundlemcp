import { existsSync, readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

// ---------------------------------------------------------------------------
// Spec requirements — parsed verbatim out of /spec at run time, so on-screen
// cards and TESTMAP.md always quote the real requirement and cannot drift.
// ---------------------------------------------------------------------------

export interface Requirement {
  id: string;
  spec: string;
  title: string;
  text: string;
}

function findSpecDir(): string {
  let dir = process.cwd();
  for (let i = 0; i < 8; i++) {
    const candidate = join(dir, "spec");
    if (existsSync(join(candidate, "README.md"))) return candidate;
    const parent = dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  throw new Error("could not locate the /spec directory");
}

function stripMarkdown(s: string): string {
  return s
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1") // links -> their text
    .replace(/[`*]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

let cache: Map<string, Requirement> | null = null;

function allRequirements(): Map<string, Requirement> {
  if (cache) return cache;
  const dir = findSpecDir();
  const found = new Map<string, Requirement>();
  for (const file of readdirSync(dir).filter((f) => f.endsWith(".md"))) {
    const lines = readFileSync(join(dir, file), "utf8").split("\n");
    lines.forEach((line, i) => {
      // Requirements look like: `- **EP-1** ...` or `- **ADM-6 Deprovisioning:** ...`
      const m = line.match(/^- \*\*([A-Za-z]+-[0-9a-z]+)([^*]*)\*\*:?\s*(.*)$/);
      if (!m) return;
      const [, id, rawTitle, rest] = m;
      if (found.has(id)) return;
      const parts = [rest];
      for (let j = i + 1; j < lines.length; j++) {
        if (!/^\s{2,}\S/.test(lines[j])) break; // continuation lines are indented
        parts.push(lines[j].trim());
      }
      found.set(id, {
        id,
        spec: file,
        title: stripMarkdown(rawTitle).replace(/:$/, ""),
        text: stripMarkdown(parts.join(" ")),
      });
    });
  }
  cache = found;
  return found;
}

export function requirement(id: string): Requirement {
  const req = allRequirements().get(id);
  if (!req) throw new Error(`unknown requirement id "${id}" — not found in /spec`);
  return req;
}

// ---------------------------------------------------------------------------
// Scenarios — one per e2e test, keyed by a stable E2E-NN id.
// ---------------------------------------------------------------------------

// A single e2e scenario. The `E2E-NN` id threads through the test title, the
// recording filename, and TESTMAP.md, so a recording can always be traced back
// to the spec requirement(s) it verifies.
export interface Scenario {
  id: string;
  testFile: string;
  slug: string;
  title: string;
  requirements: string[];
  new?: boolean;
}

const HERE = dirname(fileURLToPath(import.meta.url));
export const SCENARIOS: Scenario[] = JSON.parse(
  readFileSync(join(HERE, "spec-map.json"), "utf8"),
).scenarios;

export function scenario(id: string): Scenario {
  const s = SCENARIOS.find((x) => x.id === id);
  if (!s) throw new Error(`unknown scenario id "${id}" — not in tests/spec-map.json`);
  return s;
}

// The primary spec of a scenario is the file that defines its first requirement.
export function primarySpec(id: string): string {
  return requirement(scenario(id).requirements[0]).spec;
}

// Resolved requirements (id + spec text) in on-screen order.
export function scenarioRequirements(id: string): Requirement[] {
  return scenario(id).requirements.map(requirement);
}

// The title Playwright shows, e.g. "E2E-07 · A UI-built endpoint serves …".
export function testTitle(id: string): string {
  return `${id} · ${scenario(id).title}`;
}

// The staged recording filename, e.g.
// "E2E-07__14-endpoints__endpoint-relay-mcp-and-audit.webm" — the spec file is
// embedded so the recording name maps straight to the spec that codes it.
export function videoName(id: string): string {
  const s = scenario(id);
  return `${id}__${primarySpec(id).replace(/\.md$/, "")}__${s.slug}.webm`;
}
