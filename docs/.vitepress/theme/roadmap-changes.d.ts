// virtual:roadmap-changes, provided at build time by ../roadmap-changes.ts
declare module "virtual:roadmap-changes" {
  import type { RoadmapChange } from "../roadmap-changes";
  const changes: RoadmapChange[];
  export default changes;
}
