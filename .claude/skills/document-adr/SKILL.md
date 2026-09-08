---
name: document-adr
description: Create or update an Architecture Decision Record (ADR) following this skill's canonical convention (docs/adr/NNNN-short-slug.md, MADR-style sections, README index). Checks the project against that convention and asks before aligning a project that differs. Use when the user says 'document this decision', 'create an ADR', 'record architecture decision', 'why did we choose X', 'document the rationale', or when a change adds a major dependency, a framework, or alters a fundamental pattern. Do NOT use for user-facing feature docs or arc42 chapters (use the arc42 skill).
allowed-tools: Read, Grep, Glob, Write, Edit, Bash, AskUserQuestion
---

# Document an Architecture Decision

Capture the "why" behind a significant technical decision as an ADR. Takes an
optional focus topic as `$ARGUMENTS`.

This skill defines **one** convention (below). It is project-independent: it
names no product, team or technology. When a repository already records
decisions differently, the skill does not silently adopt the other layout; it
lists the differences and asks whether to align the project.

## The convention

**Location and naming**

```
docs/adr/
├── README.md                 the index (table below) and the process note
├── 0001-short-slug.md
├── 0002-short-slug.md
└── ...
```

- One file per decision, `NNNN-short-slug.md`: four-digit sequential number,
  one higher than the highest existing, slug in lowercase kebab-case naming
  the decision (`0007-endpoint-profiles.md`, not `0007-decision.md`).
- The directory is append-only. A reversed decision gets a new record; the
  old record's status becomes `superseded by NNNN`. A refined decision gets a
  new record that `amends` the old one; the old record's status gains
  `(amended by NNNN)`. Accepted records are never rewritten.

**Index** (`docs/adr/README.md`), one row per record, newest last:

```markdown
| # | Decision | Status |
|---|---|---|
| [0001](0001-short-slug.md) | <decision in one line> | accepted |
```

**Record structure**

```markdown
# ADR-NNNN: <the decision as a short imperative sentence>

**Status:** proposed | accepted | superseded by NNNN · **Date:** YYYY-MM-DD · **Amends:** [ADR-XXXX](XXXX-slug.md) (optional; or **Extends:**)

## Context
The situation and the forces at play, in this repository's terms: the
components, files and constraints involved; a measurement or a failure if one
drove the decision.

## Decision drivers
- **<driver>** — why it matters here

## Decision
What was decided and where it applies in this codebase. Deviations from the
obvious or textbook answer are stated explicitly, with their reason.

## Alternatives considered
- **<alternative>** — why it was not chosen

## Consequences
### Positive
- ...
### Trade-offs
- ...
```

Rules that always hold:

- Every claim is verifiable in the repository: name the path, the symbol,
  the config key.
- Written in the team's voice as the team's decision; no tool attribution.
- Related records are referenced by id with a relative link.
- One screen of Context, one of Decision; detail lives in the code and the
  architecture documentation, which the record links to.
- If the project has architecture documentation with a decisions section
  (an arc42 chapter 9), that section mirrors the index table.

## Step 1: Check the project against the convention

```bash
ls docs/adr 2>/dev/null
ls docs/adrs docs/decisions docs/arc42/decisions doc/adr adr 2>/dev/null   # divergent locations
ls docs/adr/README.md 2>/dev/null
grep -rniE "adr|architecture decision" CLAUDE.md AGENTS.md CONTRIBUTING.md 2>/dev/null
```

Read the two newest records and the index, and compare four facts with the
convention: directory, file naming, section headings and order, index shape.

**Outcome A — the project matches, or has no ADRs yet.** Continue with
Step 2. A project with no ADRs gets `docs/adr/` and its `README.md` created
as part of the first record.

**Outcome B — the project's instructions record a deliberate deviation**
(a sentence such as "ADRs use dated file names" or "sections are
Status/Context/Decision/Reasons/Consequences" in CLAUDE.md or an equivalent
instructions file). Follow the recorded deviation without asking; it is the
project's decision.

**Outcome C — the project differs and nothing records it as deliberate.**
Stop and ask before writing anything. Present the differences as a table
(fact | project | convention) and offer exactly these options:

1. **Align the project to the convention** — the skill migrates the existing
   records: renames files, adds the missing sections (never inventing
   content; a missing section is added with a one-line note that it was not
   recorded at the time), rebuilds the index, fixes every link to a renamed
   file across the repository, and then writes the new record.
2. **Keep the project's convention** — the new record follows the project's
   layout exactly, and the skill offers to add one sentence to the project's
   instructions file recording the deviation so the question is not asked
   again.
3. **Stop** — nothing is written.

Never mix the two: a repository ends up entirely on one convention or
entirely on the other.

## Step 2: Analyze the change

```bash
git diff --name-only main...HEAD
git diff --stat main...HEAD
git log --oneline main...HEAD
```

Identify the architectural choice and the alternatives that were considered;
ask the user when the diff does not show them. Check whether an existing
record covers similar ground and decide between amending and superseding.

## Step 3: Write the record

Create `docs/adr/NNNN-short-slug.md` with the structure above. Set the status
line's `Amends`/`Extends` link when it builds on an earlier record, and flip
the earlier record's status line accordingly.

## Step 4: Index and cross-reference

- Add the row to `docs/adr/README.md`.
- Add the same row to the architecture documentation's decisions section if
  the project has one.
- Update the status row of any record this one supersedes or amends.

## Step 5: Verify

```bash
ls docs/adr/NNNN-*.md
grep '^## ' docs/adr/NNNN-*.md        # Context, Decision drivers, Decision, Alternatives considered, Consequences
grep -n 'NNNN' docs/adr/README.md docs/arc42/09-*.md 2>/dev/null
```

## Troubleshooting

| Problem | Solution |
|---|---|
| Unsure if a change warrants an ADR | If two approaches were debated, it does; if a future reader would ask "why not X?", it does |
| An existing record covers similar ground | Amend for a refinement; supersede for a reversal |
| The project has two conventions at once | That is Outcome C: show both and ask |
| Decision affects several packages | One record in `docs/adr/`, never per package |
