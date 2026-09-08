---
name: arc42
description: Write, edit, or review arc42 architecture documentation following this skill's canonical layout (docs/arc42/NN-chapter-name.md, twelve chapters, README index, Mermaid diagrams inline). Encodes the official arc42 section purposes and quality criteria. Checks the project against the layout and asks before aligning a project that differs. Use when the user says 'write arc42 chapter', 'edit arc42 documentation', 'review arc42', 'update architecture documentation', 'arc42 section X', 'improve chapter Y', 'arc42 quality check', or 'architecture documentation'. Do NOT use for ADR creation (use document-adr) or for explaining code.
allowed-tools: Read, Write, Edit, Grep, Glob, Bash, AskUserQuestion
---

# arc42 Architecture Documentation

Write, edit, or review arc42 chapters. Takes a chapter number, chapter name,
or `review` as `$ARGUMENTS`.

This skill defines **one** layout (below). It is project-independent: it
names no product, team or technology, and every chapter is written from what
the repository actually contains. When a repository already lays out its
architecture documentation differently, the skill does not silently adopt
the other layout; it lists the differences and asks whether to align.

## The convention

```
docs/arc42/
├── README.md                          index: one row per chapter, one line each
├── 01-introduction-and-goals.md
├── 02-constraints.md
├── 03-context-and-scope.md
├── 04-solution-strategy.md
├── 05-building-block-view.md
├── 06-runtime-view.md
├── 07-deployment-view.md
├── 08-crosscutting-concepts.md
├── 09-architecture-decisions.md
├── 10-quality-requirements.md
├── 11-risks-and-technical-debt.md
├── 12-glossary.md
└── diagrams/                          sources of diagrams that are not inline Mermaid
```

- Twelve chapter files, always all twelve, with exactly these names; a
  chapter that has nothing to say yet holds its title and one sentence saying
  so.
- Each file starts with `# N. <Chapter title>` and uses `## N.M <subsection>`
  headings for the subsections named below.
- Diagrams are Mermaid blocks inline in the chapter. A diagram that Mermaid
  cannot express keeps its source under `docs/arc42/diagrams/` and is
  embedded as an image next to a link to the source.
- Decisions live in `docs/adr/` (the document-adr skill's convention);
  chapter 9 mirrors that directory's index table.
- Requirements the chapters cite are linked, not copied.

## Step 1: Check the project against the convention

```bash
ls docs/arc42 2>/dev/null
ls docs/architecture doc/arc42 docs/arc42/chapters 2>/dev/null          # divergent locations
ls docs/arc42/README.md docs/arc42/diagrams 2>/dev/null
ls docs/adr 2>/dev/null
grep -rniE "arc42|architecture documentation|diagram" CLAUDE.md AGENTS.md CONTRIBUTING.md 2>/dev/null
```

Compare with the convention: directory, chapter file names and numbering,
presence of all twelve chapters, index, heading style, diagram tooling, ADR
location.

**Outcome A — the project matches, or has no architecture documentation
yet.** Continue with Step 2. A project with nothing yet gets the full
skeleton (all twelve files and the index) created before the requested
chapter is written.

**Outcome B — the project's instructions record a deliberate deviation**
(for example "diagrams are models of a diagramming tool under `docs/<tool>/`,
validated with its CLI" or "chapters live under `docs/arc42/chapters/`" in CLAUDE.md or an
equivalent instructions file). Follow the recorded deviation without asking;
it is the project's decision. Where the deviation is a diagram tool, edit
that tool's model and reference its views instead of drawing Mermaid.

**Outcome C — the project differs and nothing records it as deliberate.**
Stop and ask before writing anything. Present the differences as a table
(fact | project | convention) and offer exactly these options:

1. **Align the project to the convention** — the skill renames and
   renumbers the chapter files, creates the missing chapters as stubs,
   rebuilds the index, normalises headings, moves diagram sources under
   `docs/arc42/diagrams/`, fixes every link to a renamed file across the
   repository, and then does the requested work.
2. **Keep the project's layout** — the requested work follows the project's
   layout exactly, and the skill offers to add one sentence to the project's
   instructions file recording the deviation so the question is not asked
   again.
3. **Stop** — nothing is written.

Never mix the two: a repository ends up entirely on one layout or entirely
on the other.

## Mode: write or edit a chapter

### Step 2: Gather source material

Every claim must be verifiable in the repository. Read the real sources
before writing:

- the project's instructions files (top-level and per-package);
- build and deployment definitions (compose files, container images,
  charts, infrastructure code, CI workflows) for chapters 3 and 7;
- the source tree at depth two or three for chapter 5, and any dependency
  rule the project enforces (an import linter, an architecture test);
- `docs/adr/` for chapters 4 and 9;
- the existing chapter, so an edit keeps what is still true.

Chapters are interconnected; keep them consistent:

- Section 1 quality goals feed Section 4 (strategy) and Section 10 (scenarios).
- Section 3 boundaries define what Section 5 decomposes.
- Section 4 strategy decisions appear as ADRs in Section 9.
- Section 5 building blocks appear in Section 6 scenarios.
- Section 7 maps Section 5 blocks onto infrastructure.

### Step 3: Write following the section guidance

---

### 1. Introduction and goals

**Purpose:** the driving forces — why the system exists, who cares, which
quality attributes matter most.

- **1.1 Requirements overview** — a compact summary of the functional
  requirements and business goals; link the project's requirements or spec
  documents rather than duplicating them.
- **1.2 Quality goals** — a prioritised table of the top three to five
  quality goals, each with a concrete, measurable scenario (ISO 25010 or the
  arc42 quality model as the vocabulary). These drive Sections 4 and 10.
- **1.3 Stakeholders** — a table of role | contact | expectations covering
  everyone who must understand, build on, or decide about the architecture.

Describe the system as one product. This chapter names no technologies;
they belong in Sections 2, 4 and 5.

---

### 2. Architecture constraints

**Purpose:** where the architects have no freedom.

Tables, each row with the consequence of the constraint:

- **2.1 Technical constraints** — mandated platforms, hardware, required
  integrations.
- **2.2 Organisational constraints** — team, budget, timeline, licensing,
  regulation.
- **2.3 Conventions** — coding standards, versioning, documentation rules.

A constraint is non-negotiable; a preference belongs in Section 4.

---

### 3. Context and scope

**Purpose:** the boundary — what is inside, what is outside, what crosses it.

- **3.1 Business context** — the system as a black box with every external
  communication partner: a context diagram plus a table partner | inputs |
  outputs. Data flows, not dependencies.
- **3.2 Technical context** — the channel and protocol of each business
  interface.

Every external interface appears here; an omission becomes a blind spot in
every later chapter. Note the risk at each interface.

---

### 4. Solution strategy

**Purpose:** the fundamental "why": technology choices, decomposition, and
how each quality goal is met.

One table row per quality goal: quality goal | scenario | solution approach |
details link. Then the top-level decomposition and the organisational
decisions (repository layout, build and deployment approach), as keyword
lists. Link to Sections 5, 8 and 9.

---

### 5. Building block view

**Purpose:** the floor plan — static decomposition into modules and
components with their dependencies. Mandatory and usually the largest
chapter.

- **5.1 Level 1** — the whole system as a white box: overview diagram,
  motivation for the decomposition, a black-box description of each major
  block (responsibility, interfaces, source location), consistent with
  Section 3.
- **5.2 Level 2** — the blocks that deserve a zoom (the main service's
  internal layers or packages), same template.
- **5.3 Level 3** — only where architecturally relevant.

Map blocks to source locations with a directory tree. When the project
enforces a dependency direction, state the rule and where it is enforced.
Prefer relevance over completeness: the important, surprising, risky or
volatile blocks.

---

### 6. Runtime view

**Purpose:** how the blocks behave together.

Three to five architecturally significant scenarios — the main use cases,
critical external interactions, startup and shutdown, error handling, the key
mechanisms — as numbered steps or Mermaid `sequenceDiagram` blocks, each
naming the Section 5 blocks it touches. Partial scenarios are acceptable.

---

### 7. Deployment view

**Purpose:** software mapped onto infrastructure.

- **7.1 Infrastructure level 1** — environments, nodes, networks and
  processes, and which Section 5 blocks run where, derived from the real
  deployment definitions.
- **7.2 Infrastructure level 2** — detail for the elements that need it.

Each environment that differs (local, CI, staging, production) is documented
separately.

---

### 8. Crosscutting concepts

**Purpose:** the practices and patterns that span several blocks.

Only the concepts this system relies on, each as a `## 8.N <concept>`
section with a short real code excerpt where it clarifies and links to the
Section 5 blocks that apply it. Typical candidates: authentication and
authorisation, logging and observability, error handling, the domain model,
data formats, communication patterns, persistence, configuration,
internationalisation.

---

### 9. Architecture decisions

**Purpose:** point to the ADRs.

A sentence naming `docs/adr/` and its process, then a mirror of the ADR
index table with one extra column: id | decision | consequence in one line.
No decision content is written here.

---

### 10. Quality requirements

**Purpose:** the Section 1.2 goals expanded into measurable scenarios.

- **10.1 Quality tree** — the requirements by category, as a table or tree,
  not a repeat of Section 1.2.
- **10.2 Quality scenarios** — each with context, stimulus and a measurable
  acceptance criterion; usage, change and failure scenarios.

---

### 11. Risks and technical debt

**Purpose:** an honest, prioritised list.

- **11.1 Risks** — a table risk | impact | mitigation; resolved risks stay,
  marked resolved.
- **11.2 Technical debt** — each accepted shortcut with its reason and the
  condition under which it is paid.

---

### 12. Glossary

**Purpose:** shared vocabulary.

A table term | definition, one or two sentences each: the system's domain
terms and the technical terms stakeholders may not know. One canonical term
per concept; no common programming vocabulary.

---

### Step 4: Writing standards

- Sentence case for headings.
- No marketing language ("powerful", "seamless", "robust", "cutting-edge").
- No meta-commentary ("in this section we will discuss").
- Paragraphs over bullet lists unless a list is clearer; tables for
  stakeholders, constraints, goals, risks and glossary entries.
- Every claim verifiable in the repository; link files, ADRs and specs.
- Cross-reference related sections by number.
- The project's own writing rules, when its instructions state any,
  override this list.

### Step 5: Verify

```bash
ls docs/arc42/NN-*.md
head -3 docs/arc42/NN-*.md                                  # starts with "# N. <title>"
grep '^## ' docs/arc42/NN-*.md                              # the subsections above
grep -c 'Section [0-9]' docs/arc42/NN-*.md                  # cross-references
grep -n 'NN-' docs/arc42/README.md                          # indexed
grep -oE '\]\([^)]+\)' docs/arc42/NN-*.md | tr -d '()' | sed 's/^\]//' \
  | while read p; do [ -e "docs/arc42/$p" ] || [ -e "$p" ] || echo "Missing: $p"; done
```

## Mode: review a chapter

Check the chapter against the section guidance and report:

```markdown
## arc42 review: chapter N — <title>

### Verdict: STRONG / ADEQUATE / NEEDS WORK

### Completeness
| Required subsection | Present | Notes |
|---|---|---|

### Quality issues
Specific issues with the quoted line and a suggested fix.

### Cross-reference gaps
Connections to other sections that should exist but do not.

### Factual accuracy
Claims that do not match the repository, with the evidence.

### Convention
Deviations from the layout above, if any, and whether the project's
instructions record them as deliberate.
```

## Common mistakes

| Mistake | Fix |
|---|---|
| Vague quality goals | Add a measurable scenario |
| Section 8 covering every possible concept | Only what this system relies on |
| Section 5 listing every class | Two or three levels, relevant blocks only |
| Section 6 documenting every endpoint | Three to five significant scenarios |
| Section 9 duplicating Section 4 | Section 4 summarises strategy; Section 9 points to ADRs |
| Technologies named in Section 1 | Goals in Section 1; technology in Sections 2, 4 and 5 |
| Missing cross-references | Section 1 goals reappear in Sections 4 and 10 |
| Silently following a divergent layout | Outcome C: show the differences and ask |
