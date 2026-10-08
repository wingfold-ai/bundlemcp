# Pydantic Models, Not Dataclasses

Every structured value in this repo is a Pydantic model. `dataclasses` is not used — there are zero `@dataclass`
decorators in `packages/bundlemcp/`, and new code must not reintroduce them.

This file covers choosing a base class and configuring it. For declaring the fields themselves — descriptions,
constraints, defaults — see [pydantic-fields.md](pydantic-fields.md).

## Which base to use

| Kind of thing | Base | Lives in |
|---|---|---|
| Entity | `BaseModel` | `bundlemcp/domain/<context>/` |
| Table row of an entity | `SQLModel` (`table=True`) | `bundlemcp/infrastructure/postgres/rows/` |
| API request/response DTO | `BaseModel` | `bundlemcp/application/schemas/` |
| Everything else (results, contexts, wiring, view objects) | `BaseModel` | beside its consumer |

## The three config recipes

**Plain** — all fields are scalars or other models. No `model_config` needed.

```python
class RateResult(BaseModel):
    allowed: bool
    retry_after: int = 0
```

**Value object that must not change after construction:**

```python
class MeterContext(BaseModel):
    model_config = ConfigDict(frozen=True)
```

**Holds a runtime object** — an engine, a Valkey client, an `asyncio.Event`, a SQLModel instance, anything Pydantic has
no validator for:

```python
class CallHandle(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    cancel_event: asyncio.Event = Field(default_factory=asyncio.Event)
```

Note `Field(default_factory=...)`, not `dataclasses.field`.

## Protocol-typed fields

Pydantic builds an `isinstance` validator for unknown types, and a bare `typing.Protocol` cannot be used with
`isinstance`. The model then fails to build **at class-definition time**:

```
SchemaError: 'cls' must be valid as the first argument to 'isinstance'
```

Fix it at the protocol, not the field — add `@runtime_checkable`:

```python
@runtime_checkable
class MeteringHook(Protocol):
    async def pre_call(self, ctx: MeterContext) -> MeterDecision: ...
```

This is a capability granted to the protocol object; it adds **no requirement to implementers**, so it is safe for
published protocols that outside code implements structurally. It checks method *names*, not signatures — enough to
reject a half-implemented hook at startup rather than at first call.

Do not reach for `SkipValidation` to get around this. It produces a model whose most important fields accept anything,
which is uniformity as a costume.

## Optionality must be honest

Write `X | None` only when `None` is a real, reachable state. A field the composition root always supplies is
**required**, even if that means a longer constructor call.

The MCP edge's wiring object previously defaulted nine fields to `None` that were never `None` in practice. The cost was
not theoretical: consumers carried eight defensive guards against impossible states, and new code copied the pattern
because the type demanded it. Making them required deleted every one of those guards and made a half-wired runtime
unconstructable. `AppContainer` and `McpGatewayAssembly` follow the same rule today, and every optional field on them
names a deployment state:

| Model | `X \| None` fields | The deployment state each names |
|---|---|---|
| `AppContainer` | `token_cipher`, `upstream_tokens`, `oidc_provider` | No token encryption keys configured; no upstream OAuth; no OIDC provider configured |
| `McpGatewayAssembly` | `upstream_tokens`, `state_cipher` | No token encryption keys configured |

That is the test to apply to a new field: if you cannot name the deployment in which it is `None`, it is required.

## Data that crosses a boundary

Anything stored in Valkey, read from an external service, or handed to an outside implementer round-trips through
Pydantic — never `json.dumps` over a hand-built dict:

```python
await redis.set(key, session.model_dump_json(), ex=ttl)
...
try:
    return AdminSession.model_validate_json(raw)
except ValidationError:
    log.warning("adminsession.malformed", session_id=session_id)
    return None
```

Handle `ValidationError` explicitly at these boundaries. A stored record whose shape has drifted should degrade
predictably, not raise mid-request.

## Why this over dataclasses

Uniformity is the stated goal, but the migration paid for itself immediately: converting the edge's wiring object
surfaced a field annotated `str` that every caller had been passing an `AnyHttpUrl` to. The dataclass had hidden it
behind a `str()` call in `__post_init__` for the life of the class. Validation at the construction site is the point —
not serialization, and not speed.
