# ADR-0025: A repository per entity, a unit of work per request, one typed container

**Status:** accepted · **Date:** 2026-09-03 · **Amends:** [ADR-0020](0020-library-level-service-layer.md), [ADR-0023](0023-import-contracts-and-shared-providers.md)

## Context

Every service hand-rolled its SQLAlchemy: the by-name, get-or-raise and
paginated-list trio was copied into three services, and the same server lookup
appeared in three modules. Every mutating method ended with `await
db.commit()` and then published its invalidation event, so a publish could race
a rollback, and bootstrap, which drives three services over one session, could
leave the first two committed when the third failed. `session_scope()`
implemented exactly the missing boundary and had no caller.

The composition root published twelve loose attributes onto `app.state`;
twenty reads pulled them back untyped, four with `getattr(..., None)` fallbacks
for states that cannot occur after startup. `ServerService` defaulted three
collaborators to `None` that were never `None` in production and guarded each
use. Tests substituted collaborators by mutating the runtime after startup.

Two of the three checks for the rule that an anonymous endpoint never fronts a
per-user upstream were defined and never called.

## Decision

- **`Repository[T]`** (`store/repository.py`) holds the queries every entity
  needs: primary-key and natural-key lookup, `one`, `all`, `count`, `page`,
  `add`, `delete`. It owns no transaction.
- **`UnitOfWork`** (`store/unit_of_work.py`) pairs a session with the
  invalidation events its writes imply. `commit()` writes, then publishes, so
  no replica learns of a change that rolled back. Inside `atomic()`, inner
  commits become flushes and the scope's exit commits once; `BootstrapRunner`
  applies a whole document inside one scope. `UnitOfWorkFactory` opens one per
  request, background task or bootstrap run.
- **Services take a unit of work.** `NamedResourceService[TEntity, TRead]`
  carries list, get, delete and rename for anything addressed by name;
  `BundleService`, `ServerService` and `EndpointService` add only what is
  theirs. Services commit inside their own methods because FastAPI runs a
  yield-dependency's teardown after the response is sent, which is too late to
  fail a request.
- **Collaborators are required and typed.** `ServerService` takes a
  `ToolDiscovery`; the upstream OAuth client configuration moves to
  `UpstreamOAuthConfigService`, which takes an `UpstreamConnectionRegistry`.
  `NoopToolDiscovery` and `NoUpstreamConnections` are the null objects for
  contexts without those capabilities. `AuthService` keeps credential
  resolution; `AdminSessionService` owns the browser-session lookup, and the
  admin session store moves to `store/admin_sessions/` so services can name it.
- **The per-user-upstream rule is a policy object.** `PerUserUpstreamPolicy`
  checks it at all three edges: endpoint upsert, bundle membership and a
  server's identity switch. The latter two were previously unenforced.
- **The composed graph is one typed object.** `AppContainer` holds every
  process-wide collaborator with required fields; `CompositionOverrides` names
  the seams a test may substitute. Providers read one container field each,
  and each package's providers live in its own `providers` module.
- **The identity provider is ready by construction.**
  `JoseOidcProvider.discover(settings)` fetches the discovery document and
  returns a usable provider; there is no `preload()` to forget. It raises
  `OidcError`, not `HTTPException`.

## Reasons

- Copy-pasted queries diverge; one repository per entity cannot.
- Publishing after commit is a correctness property, not a style.
- Bootstrap is either applied or it is not.
- A service locator with `getattr(..., None)` fallbacks made impossible states
  look possible; a container with required fields makes them unconstructable.
- Substituting through the composition root keeps a test's wiring the same
  shape as production's.

## Consequences

- (+) Three services lost their private query helpers.
- (+) Closing the two unenforced edges is a correctness fix covered by tests.
- (+) A test that constructs a service passes a unit of work and fakes; no
  session handling leaks into it.
- (−) Services still own their commit. Moving the boundary to the request would
  need FastAPI to run teardown before the response, which it does not.
- (−) `create_app` takes `overrides=CompositionOverrides(...)` instead of
  loose keyword seams.
