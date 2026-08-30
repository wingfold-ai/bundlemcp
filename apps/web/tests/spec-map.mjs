// Plain-JS twin of spec-map.ts for the Node tooling (stage-recordings.mjs,
// gen-testmap.mjs), which cannot import the TypeScript module. The scenario data
// itself is single-sourced in spec-map.json; only the small /spec markdown
// parser is mirrored here. Keep the two in sync — both are ~25 trivial lines.

import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const WEB = dirname(HERE);
const REPO = dirname(dirname(WEB));
const SPEC = join(REPO, "spec");

function stripMarkdown(s) {
  return s
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/[`*]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

// id -> { spec, title, text }, parsed verbatim from /spec.
export function loadRequirements() {
  const found = new Map();
  for (const file of readdirSync(SPEC).filter((f) => f.endsWith(".md"))) {
    const lines = readFileSync(join(SPEC, file), "utf8").split("\n");
    lines.forEach((line, i) => {
      const m = line.match(/^- \*\*([A-Za-z]+-[0-9a-z]+)([^*]*)\*\*:?\s*(.*)$/);
      if (!m || found.has(m[1])) return;
      const parts = [m[3]];
      for (let j = i + 1; j < lines.length; j++) {
        if (!/^\s{2,}\S/.test(lines[j])) break;
        parts.push(lines[j].trim());
      }
      found.set(m[1], {
        spec: file,
        title: stripMarkdown(m[2]).replace(/:$/, ""),
        text: stripMarkdown(parts.join(" ")),
      });
    });
  }
  return found;
}

export function loadScenarios() {
  const data = JSON.parse(readFileSync(join(HERE, "spec-map.json"), "utf8"));
  return data.scenarios;
}

export function primarySpec(id, requirements, byId) {
  const first = byId.get(id).requirements[0];
  const req = requirements.get(first);
  if (!req) throw new Error(`unknown requirement id "${first}" for ${id}`);
  return req.spec;
}

// E2E-07__14-endpoints__endpoint-relay-mcp-and-audit.webm
export function videoName(id, requirements, byId) {
  const s = byId.get(id);
  return `${id}__${primarySpec(id, requirements, byId).replace(/\.md$/, "")}__${s.slug}.webm`;
}
