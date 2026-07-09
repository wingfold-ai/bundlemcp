# ADR-0003: SQLModel / Pydantic-first typing end to end

**Status:** accepted · **Date:** 2026-07-02

## Context

metamcp maintained three parallel shape definitions (Drizzle schema, Zod
types, frontend TS types). The maintainer wants Pydantic as the single typing
system, integrating with the database and frontend DTOs.

## Decision

Entities are defined **once** as SQLModel classes (Pydantic models that are
SQLAlchemy tables); API DTOs are Pydantic models derived from them; frontend
TypeScript types are **generated** from the FastAPI OpenAPI schema
(ARC-3/ARC-4 in [spec/01](../../spec/01-architecture.md)).

## Reasons

- One source of truth from DB row to Vue component; drift becomes a build
  error, not a runtime surprise.
- Pydantic v2 validation at every boundary for free (ARC-5).
- SQLModel classes are real SQLAlchemy models — full escape hatch for
  advanced queries.

## Consequences

- (+) No hand-written duplicate types anywhere.
- (−) SQLModel's release cadence (0.0.x) may lag SQLAlchemy features; the
  escape hatch covers this (open question in spec/01).
- (−) A codegen step joins the frontend build pipeline.
