import { existsSync, readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

// ---------------------------------------------------------------------------
// Spec requirements — parsed verbatim out of openspec/specs at run time, so
// on-screen cards and TESTMAP.md always quote the real requirement and cannot
// drift.
// ---------------------------------------------------------------------------

export interface Requirement {
  id: string;
  spec: string; // the capability, e.g. "bundles" for openspec/specs/bundles/spec.md
  title: string;
  text: string;
}

function findSpecsDir(): string {
  let dir = process.cwd();
  for (let i = 0; i < 8; i++) {
    const candidate = join(dir, "openspec", "specs");
    if (existsSync(candidate)) return candidate;
    const parent = dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  throw new Error("could not locate the openspec/specs directory");
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
  const dir = findSpecsDir();
  const found = new Map<string, Requirement>();
  for (const capability of readdirSync(dir)) {
    const file = join(dir, capability, "spec.md");
    if (!existsSync(file)) continue;
    const lines = readFileSync(file, "utf8").split("\n");
    lines.forEach((line, i) => {
      // Requirements look like: `### Requirement: EP-1 Endpoint URL`
      const m = line.match(/^### Requirement: ([A-Za-z]+-[0-9a-z]+)\s*(.*)$/);
      if (!m) return;
      const [, id, rawTitle] = m;
      if (found.has(id)) return;
      const parts: string[] = [];
      for (let j = i + 1; j < lines.length; j++) {
        if (/^#{1,4} /.test(lines[j])) break; // the text ends at the first scenario
        parts.push(lines[j].trim());
      }
      found.set(id, {
        id,
        spec: capability,
        title: stripMarkdown(rawTitle),
        text: stripMarkdown(parts.join(" ")),
      });
    });
  }
  cache = found;
  return found;
}

export function requirement(id: string): Requirement {
  const req = allRequirements().get(id);
  if (!req) throw new Error(`unknown requirement id "${id}" — not found in openspec/specs`);
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

// The primary spec of a scenario is the capability that defines its first requirement.
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
// "E2E-07__endpoints__endpoint-relay-mcp-and-audit.webm" — the capability is
// embedded so the recording name maps straight to the spec that codes it.
export function videoName(id: string): string {
  const s = scenario(id);
  return `${id}__${primarySpec(id)}__${s.slug}.webm`;
}
