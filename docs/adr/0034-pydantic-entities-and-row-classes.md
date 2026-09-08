# ADR-0034: Entities are plain Pydantic models; the persistence adapter owns the row classes

**Status:** accepted · **Date:** 2026-09-08 · **Amends:** [ADR-0003](0003-sqlmodel-pydantic-first.md), [ADR-0033](0033-clean-architecture-layers.md)

## Context

ADR-0033 kept one deviation from the layer rules: entities stayed `SQLModel`
tables with `sa_column` declarations, so `domain/` imported SQLAlchemy and the
ORM contract had to allow indirect imports. The justification was that no store
swap was planned and a mapper per aggregate was pure cost.

Reviewing that justification showed it rested on the wrong benefit. The swap
was never the main gain. The coupling had costs of its own: the domain could
not be imported without the ORM installed; `table=True` classes skip Pydantic
validation entirely, so the entities were the least validated models in the
codebase and name rules had to be duplicated as CHECK constraints and DTO
validators; entity attributes were SQLAlchemy-instrumented, which is why the
unit of work needed `refresh()` and services relied on dirty tracking. And the
reason ADR-0003 chose one class, "one definition, DB to generated TS", no longer
applied: the TypeScript types come from the `schemas/` DTOs, which were already
separate classes.

## Decision drivers

- A domain that imports only the standard library and Pydantic can be imported,
  tested and reasoned about anywhere; the driver-free contract then holds for
  both inner layers without an exception.
- Entities validated on construction catch a bad value at the boundary instead
  of at the database.
- The mapping cost is one `model_dump` / `model_validate` pair per entity, done
  once in a generic base, not a hand-written mapper per aggregate.

## Decision

- **Every entity in `domain/` is a plain `BaseModel`.** The field descriptions,
  defaults and behaviour (`McpServer.requires_per_user_token`,
  `OAuthAccessToken.is_usable`, `ApiKey.reaches`) are unchanged; the
  `__tablename__`, `__table_args__`, `sa_column`, `sa_type`, `primary_key`,
  `unique`, `index` and `foreign_key` declarations are gone. The domain
  imports neither SQLAlchemy nor SQLModel.
- **`infrastructure/postgres/rows/` holds one `SQLModel` table class per
  entity** (`McpServerRow`, `ToolRow`, …) carrying exactly those declarations.
  Importing the package registers every table on `SQLModel.metadata`; Alembic's
  `env.py` and `create_all` import it. `UtcDateTime` and `timestamp_column`
  move beside them.
- **`SqlAlchemyRepository[TEntity, TRow]` maps generically.** A row becomes an
  entity through `entity.model_validate(row, from_attributes=True)`; an entity
  becomes a row through `row(**entity.model_dump())`. `add` stages the entity
  and the staged entities are merged into the session before the next query or
  the enclosing commit, so a unit of work still sees its own writes and the
  `Repository.add` port stays synchronous. `refresh` reloads the row and copies
  the stored state back onto the entity. Compare-and-set and bulk operations
  run as statements against the row class, as before.
- **Mutations are staged explicitly.** Because entities are detached copies,
  a service that changes one calls `repository.add(entity)` before `commit`;
  the two sites that relied on dirty tracking (API-key deactivation and the
  coarse `last_used_at` write) now do.
- **The import contracts tighten.** `sqlalchemy` and `sqlmodel` join the
  driver list forbidden to `domain/` and `application/`; the separate ORM
  contract with `allow_indirect_imports` is deleted.
- **Tests that touch tables use rows.** Seeding and inspection through a raw
  session go through the row classes; the constraint tests move to
  `tests/infrastructure/test_rows.py`. Use-case tests on the memory fakes are
  unaffected, since the fakes always held plain objects.

## Alternatives considered

- **Keep SQLModel entities (ADR-0033's deviation)** — rejected for the reasons
  in the context: the coupling's costs were real and the benefit it bought was
  not the one that mattered.
- **SQLModel non-table base class with a `table=True` subclass** (the
  documented SQLModel inheritance pattern) — rejected: the base still imports
  SQLModel, and column declarations cannot live on it, so the domain would
  remain ORM-dependent without gaining validation.
- **Imperative (classical) SQLAlchemy mapping of the Pydantic classes** —
  rejected: SQLAlchemy instrumentation and Pydantic's attribute handling do not
  compose reliably, and it would re-introduce instrumented domain objects.
- **Making `Repository.add` asynchronous and merging immediately** — rejected:
  every service call site would change for no gain; staging and flushing before
  the next read gives the same semantics.

## Consequences

### Positive

- `domain/` imports only the standard library and Pydantic; all four import
  contracts hold with no indirect-import exception.
- Entities validate on construction.
- Repositories return detached plain objects, so nothing outside
  `infrastructure/postgres/` can trigger a lazy load or a flush.

### Trade-offs

- Sixteen row classes duplicate the field lists of sixteen entities; a new
  column is declared twice, in the row (with its column type) and in the entity
  (with its description).
- `add` performs a `merge`, which issues a SELECT before an INSERT for a new
  row. The management API's write volume makes this irrelevant; the audit
  writer bypasses it by constructing rows directly.
- A mutation that is not followed by `add` is silently lost instead of
  persisted by dirty tracking. The fakes behave the same way, so a use-case
  test catches the omission.
