# 62 — Architecture documentation (arc42 + ADR + LikeC4)

**Status:** Accepted · **Origin:** new (user requirement)

## Summary

The architecture is documented in the **arc42** structure, decisions are recorded as **ADRs** (with reasons and
consequences), and all structural diagrams come from a single **LikeC4** model. The `/spec` folder defines *what* the
system must do; `docs/arc42` explains *how and why* it is built that way. Both are maintained continuously.

## Requirements

- **ADOC-1 arc42:** `docs/arc42/` contains the 12 standard arc42 sections as numbered Markdown files
  (01-introduction-and-goals … 12-glossary). Sections reference specs by requirement ID instead of duplicating normative
  content; arc42 carries rationale, views, and cross-cutting concepts.
- **ADOC-2 ADRs:** `docs/adr/` holds Architecture Decision Records in MADR style — `NNNN-title.md` with
  **Status / Context / Decision drivers / Decision / Alternatives considered / Consequences** (Consequences split into
  Positive and Trade-offs; a section whose content was not recorded at the time says so in one line) — indexed from
  arc42 §9 (Architecture Decisions). ADRs are append-only: a later decision MUST NOT edit an earlier record's Context,
  Decision or Consequences, only its status line. Two states express the relationship, and both MUST be recorded on the
  **earlier** record, because that is the one a reader arrives at: `superseded by NNNN` when the decision is wholly
  replaced and MUST NOT be followed, and `accepted` with `Amended by: NNNN` when it was partly revised and both records
  still apply. Every `Amends:` MUST have a matching `Amended by:` on each ADR it names, and the arc42 §9 index MUST
  agree with the files.
- **ADOC-3 LikeC4:** `docs/likec4/` holds the LikeC4 model (`*.c4`): one model of actors/systems/containers and named
  views for **context**, **container**, and **deployment**. This model is the *single source* for structural diagrams —
  arc42 §3 (context), §5 (building blocks), §7 (deployment) and the user docs ([DOC-4](61-docs-and-onboarding.md)) embed
  these views; no hand-drawn duplicates.
- **ADOC-4** Diagram rendering: the LikeC4 CLI (or VS Code extension) renders the views; CI SHOULD validate that the
  model parses (`likec4` build) so broken diagrams fail fast.
- **ADOC-5** Process: any change that makes or reverses an architectural decision MUST land with an ADR in the same PR;
  structural changes update the LikeC4 model in the same PR. Spec files link the ADR where a requirement encodes a
  decision (e.g. Streamable-HTTP-only → ADR-0005).
- **ADOC-6** Seed content: the initial commit of `docs/` includes arc42 sections filled from the current specs, ADRs
  0001–0010 covering the decisions already taken (rewrite-not-fork; FastMCP v3; SQLModel/ Pydantic-first; Postgres+Redis
  state split; Streamable-HTTP-only; OIDC-only admin auth; endpoint profiles incl. ChatGPT re-annotation;
  full-bidirectional proxy; endpoint-bound tokens + consent; single workspace), and the LikeC4 model with the three
  views.

## Out of scope

- Generated API reference (OpenAPI serves that — [API-3](40-management-api.md)).
- Publishing the arc42 docs as a website (in-repo Markdown for v1).

## Open questions

- None.
