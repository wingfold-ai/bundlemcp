# ADR-0026: Controllers own an HTTP surface

**Status:** accepted · **Date:** 2026-09-03 · **Amends:** [ADR-0019](0019-api-service-layer.md)

## Context

Each management resource was a module of free route functions on an
`APIRouter`, every one of which re-declared the `_auth: ServiceAuthProvider`
parameter to be protected. The rule that every management route is
authenticated was a convention each function had to remember, and the
health probes were closures inside the app factory.

## Decision

- **A `Controller` base class (`bundlemcp/http/controller.py`) declares one
  HTTP surface.** A subclass names its `prefix` and `tags` and marks handler
  methods with `@route.get` and friends, which record the verb, path and
  FastAPI options on the method; constructing the controller binds each
  recorded method, bound to the instance, through `add_api_route` in the
  order the decorators were written. FastAPI's own decorators cannot be used
  in a class body: there is no router yet and the method is unbound, so
  `self` would surface as a query parameter. The recording decorator keeps
  the familiar look while the base class does the binding.
- **Shared policy is a router-level dependency.** `ManagementController`
  attaches the admin-session-or-service-key check once, so no route under it
  can forget authentication. Public surfaces derive from `Controller`
  directly, so the absence of the policy is visible in the class line.
- **`bundlemcp/http/` is a new layer** beside `providers/` in the import
  contract: FastAPI glue that `api/`, `gateway/` and `oauth/` may all consume,
  importing nothing above `services/`.
- The management API's eight resources, `/me` and the health probes are
  controllers under `api/controllers/`. The OAuth routes and the MCP endpoint
  keep their routers for now and follow in their own changes.

## Reasons

- A controller makes the policy of a surface a property of the surface, not a
  convention every route re-states.
- A class per surface is where a reviewer expects to find its routes.

## Consequences

- (+) No route can be mounted under the management prefix without
  authentication.
- (+) The app factory lists surfaces, not routes.
- (−) A new delivery package must place itself relative to `bundlemcp.http`
  in the layer contract.
