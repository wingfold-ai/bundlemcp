---
name: clean-architecture
description: Evaluate, design, build, or refactor a codebase according to Clean Architecture with four layers — domain (core), application, infrastructure, and api (this project's name for the presentation layer) — and strict inward-pointing dependencies. Use this skill whenever the user mentions clean architecture, onion architecture, hexagonal / ports-and-adapters, layered architecture, dependency rule, repository interfaces, swapping persistence (SQL ↔ NoSQL), "how well structured is this project", "audit the architecture", "refactor into layers", scaffolding a new service/backend, or asks for an architecture diagram of a project. Also use it when the user asks where a class/module "belongs" or complains that business logic is coupled to a framework or database — even if they never say "clean architecture".
---

# Clean Architecture (domain / application / infrastructure / api)

This skill turns Clean Architecture into concrete, checkable rules for one specific layout, and gives you three workflows on top of it: **evaluate** an existing project, **build** a new one, and **refactor** a project toward it. It also produces the classic concentric-rings diagram with the project's actual modules placed in the rings.

The only deviation from textbook Clean Architecture: the presentation layer is called **`api`**. Everything else (dependency rule, boundary crossing with DTOs, ports owned by the inside) is standard.

## The four layers in one screen

```
api  ──►  application  ──►  domain
                ▲
         infrastructure   (implements application's ports)

composition root (main / bootstrap)  ──►  all of the above
```

| Layer | Contains | May import from | Must never import |
|---|---|---|---|
| **domain** | entities, value objects, domain services (pure rules across entities), domain events, domain exceptions, invariants | nothing but the language stdlib | application, infrastructure, api, any framework, ORM, SDK |
| **application** | use cases / handlers (orchestration), **ports** (repository + gateway interfaces), input/output DTOs, unit-of-work interface, application exceptions, application-level authorization | domain | infrastructure, api, any framework, ORM, SDK |
| **infrastructure** | implementations of ports: `PostgresOrderRepository`, `MongoOrderRepository`, `StripePaymentGateway`, `SmtpEmailSender`, ORM models, migrations, caches, message-bus clients, config loading | application (ports, DTOs), domain | api |
| **api** | HTTP controllers/routers, GraphQL resolvers, gRPC handlers, CLI commands, message consumers, request/response schemas, auth middleware, mapping request → command DTO → use case → response | application (use cases, DTOs), domain (types only, sparingly) | infrastructure |
| **composition root** | wiring: instantiates infrastructure adapters, injects them into use cases, hands use cases to api | everything | — |

Two things people get wrong, so hold the line on them:

- **Application services are not infrastructure.** `PlaceOrder` (load → build → price → charge → save → commit) is a business process expressed against interfaces; it does not change when Postgres becomes Mongo. It lives in `application/`. Infrastructure is only the technology-specific implementations.
- **Domain service vs application service.** Domain service = pure rule involving several entities, unit-testable with no mocks (`PricingService.calculate_total(order, customer)`). Application service = script that sequences I/O through ports and calls domain logic; it contains no business rules of its own. If a use case grows an `if customer.tier == "gold"` branch, a rule has leaked out of the domain.

For the full per-layer rules, what goes where, the ports convention, and boundary-crossing rules, read `references/layer-rules.md`.

## Workflow 1 — Evaluate an existing project

Goal: an honest, evidence-based report of how well the project fits this architecture, not a lecture on theory.

1. **Map the tree to layers.** List the top-level source folders. Assign each to domain / application / infrastructure / api / composition root / unmapped. Projects rarely use these exact names; `core`, `models`, `services`, `repositories`, `routes`, `handlers`, `db` all need judgement. Record the mapping explicitly — it's the first thing the user will disagree with if you got it wrong.
2. **Scan imports.** Run `scripts/scan_imports.py` with the mapping (works for Python, TypeScript/JavaScript, Go, Java, C#, Kotlin). It emits every cross-layer edge and flags the ones that violate the table above. Read the flagged files yourself; the script is a heuristic and will occasionally misclassify.
3. **Check the structural signals** in `references/evaluation.md` — ports declared inside vs outside, DTOs at the boundary, domain purity, whether the composition root exists or wiring is scattered, whether infrastructure could be swapped by touching one folder.
4. **Score and report** using the rubric and template in `references/evaluation.md`. Lead with the two or three findings that matter most; list the rest. For each violation give file, line, what it imports, and the one-line fix direction.
5. **Draw the diagram** (Workflow 4) with the real modules and the violation edges in red. A picture of the current state next to the target state is usually the most persuasive thing in the report.

Do not penalise a project for not using the literal folder names. Penalise dependency direction, leaked business rules, and framework types crossing boundaries.

## Workflow 2 — Build from scratch

1. **Start from the domain.** Identify entities, value objects and the invariants they protect. Write them with no framework imports. If the user only describes endpoints, ask what the nouns and rules are first; a domain designed from an HTTP surface ends up anaemic.
2. **Write the use cases and their ports.** One use case per user intention (`PlaceOrder`, `CancelSubscription`, `GetInvoice`). For each, list the ports it needs (`OrderRepository`, `PaymentGateway`, `Clock`). Declare the ports in `application/ports/` as interfaces / protocols / abstract classes. Define input command/query DTOs and output DTOs.
3. **Implement one adapter per port** in `infrastructure/`, grouped by technology (`infrastructure/postgres/`, `infrastructure/stripe/`). Also write an in-memory fake for every repository port — it's what use-case tests will use, and it proves the port is technology-agnostic.
4. **Add the api layer.** Controllers map request → command DTO, call the use case, map result DTO → response. No business logic, no repository access, no ORM models.
5. **Write the composition root** (`main.py`, `main.go`, `Program.cs`, a `container.ts`). This is the only place concrete infrastructure classes are named next to use cases.
6. **Add guardrails**: an import-linter / dependency-cruiser / ArchUnit rule set encoding the table above, and a test that boots every use case with in-memory fakes. Suggested configs are in `references/layer-rules.md`.
7. **Draw the diagram** so the user sees the intended structure before the code grows.

Use the folder skeleton in `references/layer-rules.md` as the default; adapt naming to the language's conventions, not the other way round.

## Workflow 3 — Refactor toward Clean Architecture

Refactoring everything at once fails. Work in vertical slices and keep the build green.

1. **Run Workflow 1 first.** You need the map and the violation list; the report is your backlog.
2. **Create the four folders and the composition root** even if they're nearly empty. Move code only when a slice is being worked.
3. **Pick one slice** — a single endpoint or job with the most change pain. For that slice:
   - extract the pure rules into `domain/` (entities, value objects, a domain service if rules span entities);
   - define the port(s) it needs in `application/ports/`, extracted from whatever concrete class it currently calls;
   - move the orchestration into a use case in `application/`, taking ports through the constructor;
   - move the concrete class (ORM repo, HTTP client) into `infrastructure/` and make it implement the port;
   - reduce the controller to mapping + one use-case call, and move it into `api/`;
   - wire it in the composition root;
   - add a use-case test with in-memory fakes.
4. **Repeat** slice by slice. After every slice the dependency scanner should report fewer violations, never more.
5. **Turn on the guardrail linter** once the violation count is low enough that it can pass; from then on it blocks regressions.

The step-by-step mechanics for common starting points (fat controllers, Active Record models, service classes that do everything, framework DI containers everywhere) are in `references/refactoring.md`.

## Workflow 4 — Produce the architecture diagram

The diagram is the Clean Architecture concentric rings: **domain** as the core circle, **application** as the middle ring, and the outer ring split into **api** (top half) and **infrastructure** (bottom half). API and infrastructure share a ring because both depend inward only and neither depends on the other — drawing infrastructure inside api would falsely suggest api depends on it. A thin outermost band holds the composition root.

Inside each ring, place the project's **modules** — the sub-folders of the layer folder (`infrastructure/postgres`, `application/orders`, `api/http`), not individual classes — unless a layer is so small that its classes are its modules. Use the module's folder name, optionally with one or two notable items underneath (`postgres` → `OrderRepository, UnitOfWork`).

Generate it with `scripts/render_diagram.py`: write a small JSON describing the modules per layer (and optional violation edges), and the script emits an SVG. The JSON schema, layout rules, colours, and how to draw current-vs-target are in `references/diagram.md`. If the script can't be run in the current environment, hand-write the SVG following the same spec.

Always include a one-line legend: *arrows and dependencies point inward; outer rings know about inner rings, never the reverse.*

## Quick decision test for "where does this go?"

- Would it still be correct if the database, web framework and every SDK were replaced? Pure rule → **domain**.
- Does it sequence steps and touch I/O only through interfaces? → **application**.
- Does it import a driver, ORM, SDK, or protocol library to *implement* an interface? → **infrastructure**.
- Does it parse a request or serialise a response? → **api**.
- Does it name concrete infrastructure classes and hand them to use cases? → **composition root**.

## References

- `references/layer-rules.md` — detailed contents of each layer, ports convention, DTO rules, default folder skeleton, linter configs per language.
- `references/evaluation.md` — audit procedure, structural signals, scoring rubric, report template.
- `references/refactoring.md` — slice-based migration playbook for common legacy shapes.
- `references/diagram.md` — diagram spec and JSON schema for `scripts/render_diagram.py`.
- `scripts/scan_imports.py` — cross-layer import scanner; outputs JSON edges + violations.
- `scripts/render_diagram.py` — concentric-rings SVG renderer.
- `assets/example-layers.json`, `assets/example-mapping.json` — worked examples for the two scripts.
