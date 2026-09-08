# Evaluating a project against Clean Architecture

Contents
1. Procedure
2. Layer-mapping heuristics
3. Structural signals to check
4. Scoring rubric
5. Report template

---

## 1. Procedure

1. Inventory the source tree (`find`/`tree`, depth 2–3). Ignore build output, vendored deps, generated code.
2. Produce the **layer mapping** (§2). Write it down as JSON — the scanner needs it and the report shows it.
3. Run the scanner:
   ```
   python scripts/scan_imports.py <src_root> --mapping mapping.json --out edges.json
   ```
   It prints a summary and writes all cross-layer edges with `violation: true/false`.
4. Open every violating file. Confirm the edge is real (not a type-only import, not a test file) and classify it (§4 categories).
5. Walk the structural signals (§3) — these catch problems imports don't show.
6. Score (§4), write the report (§5), render current-state diagram with violations (`references/diagram.md`), and where useful a target-state diagram.

Keep the whole thing proportionate: a 20-file project gets a one-page report; a 400-file one gets sections.

---

## 2. Layer-mapping heuristics

Real projects don't use the canonical names. Map by *content*, then confirm by *imports*.

| Seen folder / pattern | Likely layer | Confirm by |
|---|---|---|
| `domain`, `core`, `model(s)`, `entities` | domain | no framework imports inside |
| `application`, `usecases`, `services`, `handlers`, `commands`, `queries`, `interactors`, `workflows` | application | imports domain, takes interfaces in constructors |
| `services` that import the ORM directly | *mixed* application+infrastructure | flag as a finding |
| `infrastructure`, `infra`, `adapters`, `persistence`, `repositories` (concrete), `db`, `clients`, `gateways`, `external` | infrastructure | imports drivers/SDKs |
| `repositories` containing only interfaces | application (ports) or domain | no driver imports |
| `api`, `presentation`, `web`, `http`, `controllers`, `routes`, `routers`, `handlers` (HTTP), `graphql`, `cli`, `consumers`, `views`, `resolvers` | api | imports web framework |
| `main.*`, `app.*` (framework app factory), `bootstrap`, `container`, `di`, `wiring`, `Program.cs`, `Startup.cs` | composition root | instantiates concrete classes |
| `shared`, `common`, `utils`, `lib` | depends — often a dumping ground | inspect; may need splitting into domain/shared vs infrastructure/shared |
| `config`, `settings` | infrastructure (loading) | — |
| `schemas`, `dto`, `serializers` next to controllers | api | — |
| `dto` next to use cases | application | — |
| `tests` | ignore for dependency rules; check that use-case tests don't require a DB | — |

Mapping JSON format expected by the scanner:
```json
{
  "domain": ["src/domain", "src/core/model"],
  "application": ["src/application", "src/services"],
  "infrastructure": ["src/infrastructure", "src/db", "src/clients"],
  "api": ["src/api", "src/routes"],
  "composition_root": ["src/main.py", "src/container"]
}
```
Paths are prefixes relative to the scan root. A file that matches no prefix is reported as `unmapped` and does not produce violations, but a large unmapped set is itself a finding.

---

## 3. Structural signals to check

Imports show direction; these show whether the layers are doing the right job.

**Domain purity**
- Entities/value objects import only stdlib (or accepted pure libs). Check for ORM base classes, column decorators, JSON serialisers, HTTP types.
- Domain objects have behaviour (methods enforcing invariants), not just fields.
- Rules live here. Grep the application and api layers for business-y conditionals (`if status ==`, tier/discount logic, date arithmetic on business dates) and check whether they should be domain methods.

**Ports and inversion**
- Repository/gateway interfaces exist and are declared in application (or domain), not in infrastructure.
- Use cases receive ports through constructors/parameters — not by importing a concrete class, not via a global/service locator.
- Port signatures use domain types; no `Session`, `Connection`, `Query`, `Document` types leak into them.
- At least one in-memory implementation exists per repository port (strong signal of a genuinely abstract port).

**Boundary crossing**
- Controllers construct command DTOs; they don't pass the framework `Request` or the raw body dict/JSON into use cases.
- Use cases return DTOs or domain values, not ORM models or framework responses.
- Responses are built from DTOs; entities are not serialised directly.

**Composition root**
- One identifiable place wires concrete → abstract. Concrete infrastructure class names appear in the composition root and inside infrastructure only.
- Grep for `new PostgresX`, `XRepository(` etc. outside those places.

**Swap test (the user's own criterion)**
Pick the primary persistence. Ask: to replace it with a different store, which files change? Correct answer: files under `infrastructure/<tech>/` plus one line in the composition root. List every other file that would need to change — each is a finding.

**Testability**
- Use-case tests run without a database/network. If `tests/` needs docker or a live DB for everything, the ports are missing or bypassed.

**api layer thinness**
- Controllers contain no repository calls, no ORM queries, no business branching. Count lines per controller method; anything past ~15 lines is suspicious.

---

## 4. Scoring rubric

Score each dimension 0–4; report the total out of 24 and the letter band. Also list violations by category with counts. Scores are for orientation; the findings are the deliverable.

| Dimension | 0 | 2 | 4 |
|---|---|---|---|
| **Dependency direction** | inward rule broadly ignored; cycles between layers | a handful of violations, mostly in one layer | zero violations, linter enforces it |
| **Domain purity & richness** | domain absent or Active Record / ORM models double as entities | entities exist but anaemic or with some framework coupling | pure, behaviour-rich entities/VOs; rules live here |
| **Ports & inversion** | use cases call concrete infrastructure directly | interfaces exist but declared in infrastructure, or not consistently injected | ports owned by application, injected, in-memory fakes exist |
| **Boundary crossing** | framework requests / ORM rows pass through layers | DTOs used in some places | DTOs at every boundary, entities never serialised directly |
| **Composition root** | wiring scattered; `new Concrete()` in use cases/controllers | wiring mostly centralised, some leakage | single composition root; concrete names appear nowhere else |
| **Swappability (swap test)** | replacing the DB touches domain/application/api | touches infrastructure plus a few stray files | touches only `infrastructure/<tech>/` and the composition root |

Bands: 21–24 **A** (clean; maintain with linter) · 15–20 **B** (sound; targeted fixes) · 9–14 **C** (layered in name, coupled in practice; slice-based refactor) · 0–8 **D** (no effective layering; treat as greenfield in Workflow 3).

Violation categories to tag each finding with:
- `DEP-INWARD` — inner layer imports outer (domain→application, application→infrastructure/api).
- `DEP-SIBLING` — api↔infrastructure import.
- `DEP-FRAMEWORK` — domain or application imports framework/ORM/SDK.
- `LEAK-RULE` — business rule found outside domain.
- `LEAK-TYPE` — framework/ORM type crosses a boundary (in a port signature, DTO, or use-case return).
- `PORT-MISSING` — use case depends on a concrete adapter.
- `PORT-MISPLACED` — interface declared in infrastructure.
- `WIRING-SCATTERED` — concrete construction outside the composition root.
- `ANEMIC` — domain object without behaviour where rules exist elsewhere.
- `UNMAPPED` — significant code that fits no layer.

---

## 5. Report template

Use this shape; drop sections that would be empty.

```markdown
# Architecture assessment — <project>

**Score: <n>/24 (band <A–D>)** — <one sentence verdict>.

## Layer mapping
| Folder | Layer | Notes |
|---|---|---|
| src/models | domain (mixed with ORM) | entities are SQLAlchemy models |
| ... | ... | ... |

## Top findings
1. **<headline>** (`CATEGORY`) — what, where (file:line), why it matters, fix direction.
2. ...
3. ...

## Dependency violations
| # | Category | From | To | Fix |
|---|---|---|---|---|
| 1 | DEP-FRAMEWORK | src/domain/order.py:3 | sqlalchemy | map in infrastructure/postgres/models.py, keep Order pure |
| ... |

## Swap test: <current store> → <alternative>
Files that would change: <list>. Expected: infrastructure/<tech>/ + composition root only.

## Scores
| Dimension | Score | Evidence |
|---|---|---|
| Dependency direction | 2/4 | 6 violations, all in services/ |
| ... |

## Recommended order of work
1. <first slice / first fix and why>
2. ...

## Diagrams
- current-state.svg (violations in red)
- target-state.svg
```

Tone: specific, evidence-first, no theory lectures. Every finding needs a file path. Praise what is already right in one line — it tells the user what not to break.
