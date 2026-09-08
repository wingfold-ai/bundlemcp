# Layer rules

Contents
1. The dependency rule
2. domain
3. application
4. infrastructure
5. api
6. Composition root
7. Ports convention
8. Boundary-crossing rules (DTOs)
9. Default folder skeleton
10. Guardrail linter configs

---

## 1. The dependency rule

Source code dependencies point **inward** only. "Inward" means toward `domain`.

```
api ──────────► application ──────────► domain
infrastructure ► application ──────────► domain
composition root ► api, infrastructure, application, domain
```

Allowed / forbidden matrix (row imports column):

| from \ to | domain | application | infrastructure | api | framework/ORM/SDK |
|---|---|---|---|---|---|
| domain | ✓ | ✗ | ✗ | ✗ | ✗ |
| application | ✓ | ✓ | ✗ | ✗ | ✗ |
| infrastructure | ✓ | ✓ | ✓ | ✗ | ✓ |
| api | ✓ (types) | ✓ | ✗ | ✓ | ✓ (web framework only) |
| composition root | ✓ | ✓ | ✓ | ✓ | ✓ |

"Framework/ORM/SDK" means anything that is not the language's standard library or a pure utility library (a date library, a validation library with no I/O). Pragmatic exceptions: a dataclass/record decorator, a typing library, an `attrs`/`pydantic` model used purely as a value container. If the project uses pydantic in the domain, note it but do not fail the audit for it alone.

Inner layers never *know* outer layers exist. That is what lets the outer layer be replaced.

---

## 2. domain

**Purpose:** the business rules, expressed in the business's language, independent of any delivery or storage mechanism.

Contains:
- **Entities** — objects with identity and a lifecycle (`Order`, `Customer`). Methods enforce invariants (`order.add_line(...)` refuses to add to a shipped order).
- **Value objects** — immutable, compared by value (`Money`, `EmailAddress`, `OrderId`). Validate on construction.
- **Aggregates** — an entity that is the consistency boundary for a cluster (`Order` owns its `OrderLine`s). Repositories load/save aggregates, not individual children.
- **Domain services** — pure rules that involve several entities and don't naturally belong to one (`PricingService`, `TransferPolicy`). Stateless. No I/O. Unit-testable with zero mocks.
- **Domain events** — facts that happened (`OrderPlaced`). Plain data. Raised by aggregates, published later by the application layer.
- **Domain exceptions** — `InsufficientStock`, `InvalidTransition`.
- Optionally **repository interfaces** (see §7). Default in this skill: they live in `application/ports/`; accept `domain/` if the project already does that consistently.

Does not contain: anything that mentions HTTP, JSON, SQL, tables, columns, files, environment variables, clocks (inject a `Clock` port), random numbers (inject), the current user (pass it in).

Smell checklist:
- Entity has `save()` / `find()` methods → Active Record; that's infrastructure leaking in.
- Entity fields carry ORM column annotations → domain is coupled to persistence.
- Domain object serialises itself to JSON → presentation leaking in.
- Getters and setters only, no behaviour → anaemic domain; rules are probably in the application layer or controllers.

---

## 3. application

**Purpose:** what the system *does* — the use cases — orchestrated against abstractions.

Contains:
- **Use cases / handlers / application services** (interchangeable terms). One per user intention. Structure: receive command DTO → load via ports → call domain → persist via ports → commit → return result DTO. Constructor takes ports; no service-locator lookups.
- **Ports** — interfaces the use cases depend on: repositories (`OrderRepository`), gateways (`PaymentGateway`, `EmailSender`), infrastructure abstractions (`Clock`, `IdGenerator`, `UnitOfWork`, `EventPublisher`).
- **DTOs** — commands (`PlaceOrderCommand`), queries (`GetInvoiceQuery`), results (`OrderSummary`). Plain data; no behaviour beyond validation of shape.
- **Application exceptions** — `OrderNotFound`, `NotAuthorized`.
- **Application-level policy** — authorization ("can this principal place orders?"), idempotency, transaction boundaries, publishing domain events after commit.
- If CQRS is used: `commands/` and `queries/` sub-folders; query handlers may use a read-model port that returns DTOs directly.

Does not contain: business rules (move to domain), concrete adapters (move to infrastructure), request/response handling (move to api).

The test for this layer: every use case can be executed in a unit test with in-memory fakes of its ports and runs in milliseconds.

---

## 4. infrastructure

**Purpose:** concrete implementations of the application's ports, plus the technology plumbing they need.

Contains, grouped **by technology**:
- `postgres/` — `PostgresOrderRepository implements OrderRepository`, ORM models / mappers, `SqlAlchemyUnitOfWork`, migrations.
- `mongo/` — `MongoOrderRepository implements OrderRepository`.
- `stripe/` — `StripePaymentGateway implements PaymentGateway`.
- `smtp/`, `sendgrid/` — `EmailSender` implementations.
- `redis/` — caches, `RedisIdempotencyStore`.
- `kafka/`, `rabbitmq/` — `EventPublisher` implementations (outbound only; inbound consumers are `api`).
- `memory/` or `fakes/` — in-memory implementations of every repository/gateway port. These are first-class, not test junk: they prove the ports are technology-neutral and they power fast use-case tests.
- `config/` — settings loading (env vars, files). The composition root reads these.
- `system/` — `SystemClock`, `UuidGenerator`.

**Mapping is infrastructure's job.** An ORM model is not a domain entity. `PostgresOrderRepository.get()` loads rows and constructs a domain `Order`; `save()` does the reverse. If the ORM model *is* the entity, swapping the database means rewriting the domain — the exact failure this architecture exists to prevent.

Swapping SQL → NoSQL correctly touches: `infrastructure/postgres/` (delete or keep), `infrastructure/mongo/` (add), the composition root (one line). Nothing in application, domain, or api changes. If anything else has to change, that's a violation to report.

---

## 5. api

**Purpose:** the presentation / delivery layer — everything that receives input from the outside world and hands it to a use case.

Contains, grouped by protocol or entrypoint:
- `http/` — routers/controllers, request & response schemas, error-to-status mapping, auth middleware, OpenAPI wiring.
- `graphql/` — resolvers, schema.
- `grpc/` — service handlers, proto mapping.
- `cli/` — commands.
- `consumers/` — message-queue / event consumers (inbound). They are an entrypoint just like an HTTP route.
- `jobs/` — scheduled jobs (cron entrypoints).

A controller does exactly this: parse/validate request → build command DTO → call use case → map result DTO or application exception → response. Nothing else. No repository access, no ORM queries, no `if` on business state.

`api` may import `domain` for types (e.g. an `OrderId` value object in a path parameter). Prefer DTOs; never expose entities directly in responses.

---

## 6. Composition root

The one place concrete classes meet abstractions. `main.py` / `main.go` / `Program.cs` / `container.ts` / a Spring `@Configuration`.

```python
# main.py
settings = load_settings()
engine = create_engine(settings.db_url)
orders = PostgresOrderRepository(engine)          # infrastructure
payments = StripePaymentGateway(settings.stripe)   # infrastructure
place_order = PlaceOrder(orders, payments, SystemClock())  # application
app = build_http_app(place_order=place_order)      # api
```

If the framework has a DI container, use it *here* and only here. Use cases should not know the container exists.

Smell: `new PostgresOrderRepository()` or `container.resolve(...)` appearing anywhere outside this file/folder.

---

## 7. Ports convention

- A port is an interface **owned by the layer that uses it** (application), named for its role, not its technology: `OrderRepository`, never `PostgresOrderRepository` as an interface name.
- Repository ports speak in aggregates and domain types: `get(order_id: OrderId) -> Order`, `add(order: Order)`. No query strings, no table names, no ORM types in the signature.
- Keep ports small; one per role. A `Database` port with 40 methods is a leaked implementation.
- Every port has at least two implementations conceptually: the real one and an in-memory fake. If a port can only ever have one implementation, question whether it's a port.
- Place: `application/ports/` (default). Alternative accepted: repository interfaces in `domain/`, other ports in `application/ports/`. Never in `infrastructure/`.

Language forms: Python `typing.Protocol` or `abc.ABC`; TypeScript `interface`; Go `interface` declared in the consuming package; Java/C#/Kotlin `interface`.

---

## 8. Boundary-crossing rules (DTOs)

Data that crosses a layer boundary is a **simple structure**: dataclass, record, struct, plain object. Not an entity, not an ORM row, not a framework request.

- api → application: command / query DTOs.
- application → api: result DTOs (or domain value objects for trivial cases).
- application ↔ infrastructure: domain entities/aggregates through repository ports (the port's signature *is* the contract).
- infrastructure ↔ database: ORM models / documents, mapped to and from domain inside infrastructure.

Reason: if a controller passes its `Request` object into a use case, the use case now depends on the web framework; if a use case returns an ORM model, the api layer depends on the database.

---

## 9. Default folder skeleton

Adapt names to language conventions (`snake_case` for Python/Go packages, `kebab-case` or `camelCase` for TS, `PascalCase` for C#), but keep the four layer folders literal so the dependency linter can key off them.

```
src/                        (or the service name)
  domain/
    orders/
      order.py              # aggregate root
      order_line.py
      order_id.py           # value object
      events.py             # OrderPlaced, OrderCancelled
      exceptions.py
    customers/
    pricing/
      pricing_service.py    # domain service
    shared/
      money.py              # shared value objects
  application/
    ports/
      order_repository.py
      customer_repository.py
      payment_gateway.py
      email_sender.py
      unit_of_work.py
      clock.py
    orders/
      place_order.py        # use case + PlaceOrderCommand + result DTO
      cancel_order.py
      get_order.py
    customers/
    exceptions.py
  infrastructure/
    postgres/
      models.py             # ORM models
      order_repository.py   # PostgresOrderRepository
      unit_of_work.py
      migrations/
    stripe/
      payment_gateway.py
    smtp/
      email_sender.py
    memory/
      order_repository.py   # InMemoryOrderRepository
      ...
    system/
      clock.py
    config.py
  api/
    http/
      app.py                # framework app factory
      orders/
        router.py
        schemas.py          # request/response models
      errors.py             # exception → status mapping
      auth.py
    cli/
    consumers/
  main.py                   # composition root
tests/
  domain/                   # pure unit tests
  application/              # use-case tests with memory fakes
  infrastructure/           # adapter tests against real tech (containers)
  api/                      # contract tests with fakes injected
```

Monorepo note: if the repository has a top-level `/app` (build outputs, images, deploy) that is unrelated; the layers live under the service's source folder. Do not confuse `/app` with `application/`.

---

## 10. Guardrail linter configs

**Python — import-linter** (`.importlinter` or `pyproject.toml`):
```ini
[importlinter]
root_package = src

[importlinter:contract:layers]
name = Clean architecture layers
type = layers
layers =
    src.api | src.infrastructure
    src.application
    src.domain
```
(`|` makes api and infrastructure independent siblings; neither may import the other.)

**TypeScript — dependency-cruiser** (`.dependency-cruiser.js`, `forbidden` section):
```js
{ name: "domain-is-pure",        from: { path: "^src/domain" },        to: { pathNot: "^src/domain", path: "^src/" } },
{ name: "application-inward",    from: { path: "^src/application" },   to: { path: "^src/(api|infrastructure)" } },
{ name: "api-no-infra",          from: { path: "^src/api" },           to: { path: "^src/infrastructure" } },
{ name: "infra-no-api",          from: { path: "^src/infrastructure" },to: { path: "^src/api" } },
{ name: "domain-no-node-modules",from: { path: "^src/domain" },        to: { dependencyTypes: ["npm"] } },
```

**Go** — package structure enforces most of it (`internal/domain` cannot import `internal/api` without a cycle only if you keep interfaces in the consumer). Add `go-arch-lint` or a `depguard` config listing the same rules.

**Java/Kotlin — ArchUnit:**
```java
layeredArchitecture().consideringAllDependencies()
  .layer("Domain").definedBy("..domain..")
  .layer("Application").definedBy("..application..")
  .layer("Infrastructure").definedBy("..infrastructure..")
  .layer("Api").definedBy("..api..")
  .whereLayer("Domain").mayOnlyBeAccessedByLayers("Application","Infrastructure","Api")
  .whereLayer("Application").mayOnlyBeAccessedByLayers("Infrastructure","Api")
  .whereLayer("Infrastructure").mayNotBeAccessedByAnyLayer()
  .whereLayer("Api").mayNotBeAccessedByAnyLayer();
```

**C#** — one project per layer (`X.Domain`, `X.Application`, `X.Infrastructure`, `X.Api`) with project references matching the matrix; the compiler is the linter. NetArchTest for extra rules.
