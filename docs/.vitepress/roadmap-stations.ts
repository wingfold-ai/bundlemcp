// The shape of the roadmap's stations, written in the frontmatter of docs/roadmap.md,
// and the build-time check that every theme link reaches a page of the site.
import { existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const docsDir = resolve(dirname(fileURLToPath(import.meta.url)), "..");

export interface RoadmapTheme {
  title: string;
  note?: string;
  link?: string;
}

export interface RoadmapStation {
  title: string;
  tag?: string;
  subtitle?: string;
  /** reached and current draw a filled stop, planned a hollow one, later a dashed one */
  state: "reached" | "current" | "planned" | "later";
  /** true for the station that lists the active OpenSpec changes instead of themes */
  changes?: boolean;
  themes?: RoadmapTheme[];
}

/** Throws on a theme link that names no page, the way a dead Markdown link fails the build. */
export function assertStationLinks(stations: RoadmapStation[], page: string): void {
  for (const station of stations) {
    for (const theme of station.themes ?? []) {
      const link = theme.link;
      if (!link || /^https?:\/\//.test(link)) continue;
      const path = link.split("#")[0].replace(/^\//, "").replace(/\.html$/, "");
      const candidates = [`${path}.md`, `${path}/index.md`].map((p) => resolve(docsDir, p));
      if (!candidates.some((file) => existsSync(file))) {
        throw new Error(`${page}: roadmap theme "${theme.title}" links ${link}, which is no page`);
      }
    }
  }
}
