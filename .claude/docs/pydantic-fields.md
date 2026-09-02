# Field Declarations and Descriptions

How to declare fields on a Pydantic model. Which base class to pick and how to
configure it is a separate concern — see [pydantic-models.md](pydantic-models.md).

The rule in one line: **a `description` is API surface, not a comment.** It is
read by people and programs that never see this source file.

## Every field gets a description

There is one rule and no exemption: every field on every model carries a
`description`. A field comment that explains the field becomes that
description rather than sitting beside it — one documentation mechanism, not
two, and one that tooling can read.

On some models the description is also *published*, which raises the bar for
how it is written:

| Model | Where the description surfaces |
|---|---|
| DTOs in `schemas/` | the OpenAPI document → `/api/v1/docs`, and the TypeScript types generated for `apps/web` |
| `Settings` | operator-facing documentation of every `BUNDLEMCP_*` environment variable |
| Any tool or resource schema the gateway publishes | the prompt of the model deciding whether to call it |

For these, assume a reader who cannot see the source. For internal models — a
result object, a view struct, a wiring container — the audience is the next
maintainer, so the description can be shorter, but it is still required.

Keep `#` comments for what a description cannot carry: requirement IDs, and
notes aimed at whoever edits the line rather than whoever reads the field.

## What a good description says

**Say what the type cannot.** The type already says `int`. The description says
what the number *means* and what changes when it moves.

```python
build_timeout: int = Field(
    default=120, ge=10, le=600,
    description="Maximum seconds allowed for a single build before it is killed",
)
```

**Enumerate legal values the type cannot express**, and pair them with a
`pattern` so the value is rejected at load rather than misbehaving later:

```python
log_format: str = Field(
    default="json", pattern=r"^(json|text)$",
    description="Log output format: 'json' or 'text'",
)
```

**Give an example when the shape is not obvious.** `"Theme name (e.g. 'seriph',
'default')"` teaches more in four words than a paragraph of prose.

**Point at the authoritative list** instead of duplicating one that will drift:
"…see the servers endpoint for the full list."

**Say what a caller must do first** when order matters. If a field only makes
sense after another call, the description is where that gets stated, because
the caller may never read anything else.

**Write for the consumer, not the implementer.** Not "set by the registrar
during upsert" — say what the value does.

## Constraints go in `Field`, not in the body

Anything expressible as `ge`, `le`, `min_length`, `max_length` or `pattern`
belongs in the field. It then reaches the JSON Schema, so consumers see the
bound, and it fails at parse time with a precise error instead of surfacing as
a confusing failure deep in a handler.

```python
server_port: int = Field(default=8000, ge=1, le=65535, description="…")
```

Reserve `@field_validator` for rules that genuinely cannot be expressed
declaratively — cross-field checks, or domain rules like reserved substrings in
a name.

## Defaults go in `Field(default=...)`

Use `Field(default=…)` rather than a bare assignment on any field that also
carries a description or constraints, so the default appears in the schema
alongside them. `default_factory` for mutable defaults — never a bare `[]` or
`{}`.

## No requirement IDs in descriptions

The rule that keeps spec numbers out of docstrings applies with more force
here: descriptions are published to API consumers and to operators. `SRV-5`
means nothing to either. Keep the ID in an adjacent `#` comment and write the
description in plain terms.

```python
force: bool = Field(  # SRV-5 rename acknowledgement
    default=False,
    description="Confirm a rename that would otherwise be rejected as ambiguous",
)
```

## Function parameters as schema

When a function *is* the schema — a published tool rather than a DTO — attach
the description with `Annotated` instead of introducing a model:

```python
async def render(
    markdown: Annotated[str, Field(description="Full document source including frontmatter")],
    theme: Annotated[str | None, Field(description="Theme name; omit for the default")] = None,
) -> Result:
```

The function's docstring becomes the tool's own description, so it carries the
*when and why*; the field descriptions carry the *what* of each argument.

## Applying this

This repo currently declares fields with `Field()` in over a hundred places and
sets `description` in none of them, so `/api/v1/docs` and the generated
TypeScript client both ship bare field names. Closing that gap is worth doing
per-module as each is touched, starting with `schemas/` and `Settings` — the
two that are already published.
