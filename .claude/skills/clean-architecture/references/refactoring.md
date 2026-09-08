# Refactoring toward Clean Architecture

Contents
1. Principles
2. The slice loop
3. Playbooks by starting shape
4. Extracting a port from a concrete class
5. Detaching the domain from the ORM
6. Keeping the build green
7. When to stop

---

## 1. Principles

- **Vertical slices, not horizontal sweeps.** Moving all controllers, then all repositories, then all models leaves the system broken for weeks. Take one endpoint/job end-to-end, then the next.
- **Introduce the seam before moving the code.** Add the interface, make the existing concrete class implement it, inject it — *then* relocate files. Renames and moves are the last step of a slice, not the first.
- **Violation count only goes down.** Run `scripts/scan_imports.py` before and after each slice. A slice that adds a violation isn't done.
- **Tests before moves.** If the slice has no tests, write a characterisation test at the api boundary (request in → response out) first, so the refactor is verifiable.
- **Don't chase perfection in the domain on the first pass.** Getting the dependency direction right is the structural win; enriching an anaemic domain can follow slice by slice.

---

## 2. The slice loop

For each slice (an endpoint, a job, a consumer):

1. **Characterise.** Write or confirm a test at the boundary that captures current behaviour.
2. **Find the rules.** Read the controller/service and mark every line that is a business decision. Those go to `domain/`: as methods on an entity if they concern one aggregate, as a domain service if they span several.
3. **Find the I/O.** Mark every call to a database, HTTP client, queue, filesystem, clock, random. Each becomes a port call.
4. **Declare ports** in `application/ports/` — one interface per role, signatures in domain types (§4).
5. **Write the use case** in `application/`: constructor takes the ports; `execute(command)` does load → domain → save → commit → return DTO. Move the orchestration lines here.
6. **Make the existing concrete classes implement the ports** and move them into `infrastructure/<tech>/`. Add an in-memory fake alongside.
7. **Shrink the controller** to parse → command → use case → response; move it into `api/`.
8. **Wire** in the composition root.
9. **Test the use case** with fakes; re-run the characterisation test; re-run the scanner.
10. Commit. Next slice.

Order slices by change-pain × fan-out: start with the one the team touches most, but prefer one with low coupling to others for the first iteration so the pattern lands quickly.

---

## 3. Playbooks by starting shape

**Fat controllers** (rules + queries in route handlers)
- Steps 2–3 above will find a lot in one method. Split by intention: one use case per verb the handler serves.
- Pull request parsing into a schema/DTO first; the handler often becomes trivially small once the DTO exists.

**Active Record models** (`User.save()`, `Order.find_by(...)`, ORM base class on the entity)
- See §5. Introduce a separate pure entity, keep the ORM model as a persistence model in infrastructure, and add a mapper. The repository does the translation.
- Expect to add a repository port and implementation per aggregate you detach.

**God services** (`OrderService` with 30 methods hitting the DB directly)
- Each public method is a candidate use case. Split the class along those lines; each new use case takes only the ports it needs.
- The DB calls inside become the first repository port. Start with `get` and `add`/`save`; resist copying every SQL query as its own port method — look for the aggregate.

**Framework DI everywhere** (`@Injectable`, `@Autowired`, container lookups deep in business code)
- Constructor injection is fine and compatible. The fix is to make the *types* injected be ports (interfaces) declared in application, and to keep container registration in the composition root.
- Remove service-locator calls (`container.get(...)`) from use cases; pass the dependency in.

**Anaemic domain + service layer** (entities are structs, services do everything)
- Dependency direction may already be right. Move rules onto entities one slice at a time; the use case shrinks as the domain grows.

**Repository interfaces in infrastructure**
- Move the interface file to `application/ports/`. Nothing else changes; this is usually a five-minute win that fixes many `DEP-INWARD` violations at once.

**No layers at all** (scripts, everything in one package)
- Treat as greenfield (SKILL.md Workflow 2) but keep the old code running: build the new layered path for one slice, switch the route over, delete the old path.

---

## 4. Extracting a port from a concrete class

Given a use of a concrete class:

```python
class OrderService:
    def place(self, payload):
        repo = SqlOrderRepository(session)      # concrete
        ...
        stripe.Charge.create(amount=total)     # SDK
```

1. Write the interface the *caller* needs, in caller's terms:
   ```python
   class OrderRepository(Protocol):
       def get(self, order_id: OrderId) -> Order: ...
       def add(self, order: Order) -> None: ...

   class PaymentGateway(Protocol):
       def charge(self, customer: CustomerId, amount: Money) -> PaymentId: ...
   ```
   Only the methods this use case needs. More methods get added when another use case needs them.
2. Make the concrete class satisfy it (rename/adapt methods; wrap the SDK call in `StripePaymentGateway.charge`).
3. Change the caller to receive the interface via constructor.
4. Add `InMemoryOrderRepository` and `FakePaymentGateway`.
5. Move the concrete classes into `infrastructure/<tech>/`.

Signatures to avoid on ports: anything returning ORM models, `Session`, `Cursor`, raw dicts of rows, or taking SQL/query fragments. If the caller "needs" those, the caller has infrastructure logic in it — move that logic into the adapter.

---

## 5. Detaching the domain from the ORM

Target: `domain/orders/order.py` (pure) + `infrastructure/postgres/models.py` (ORM) + mapper inside the repository.

1. Copy the ORM model's fields into a plain entity class (dataclass/record). Add the invariant-enforcing methods that currently live in services.
2. Keep the ORM model as-is but stop using it outside infrastructure. Rename it `OrderModel`/`OrderRow` if the name clash is confusing.
3. In `PostgresOrderRepository`, write `_to_domain(model) -> Order` and `_to_model(order) -> OrderModel`. Handle children (order lines) here.
4. Switch callers to the repository port; they now receive the pure `Order`.
5. Later, if the ORM supports it, consider an imperative/classical mapping so the entity itself can be persisted without a duplicate class — an optimisation, not a requirement.

Trade-off to state plainly: you will have two classes per aggregate for a while. That duplication is the price of a swappable store and testable rules; it is not accidental.

---

## 6. Keeping the build green

- Old and new paths can coexist: keep the old service until the last slice using it is migrated, then delete.
- Use the linter in *warn* mode until the count is low, then *fail* mode. Add the config from `layer-rules.md` §10 early so the team sees the trend.
- Feature flags are rarely needed; the refactor is behaviour-preserving by construction (characterisation tests guard it).
- If the language makes moving files painful (Go packages, Java packages), do the interface + injection steps first and batch the moves per slice.

---

## 7. When to stop

Stop when:
- the scanner reports zero violations and the linter runs in CI;
- every use case has a test with in-memory fakes;
- the swap test (replace the primary store) touches only `infrastructure/<tech>/` + composition root;
- the composition root is the only file that names concrete infrastructure classes next to use cases.

Don't chase: perfect DDD aggregates, CQRS, event sourcing, or splitting into microservices. Those are separate decisions with their own costs; Clean Architecture makes them *possible*, it doesn't require them.
