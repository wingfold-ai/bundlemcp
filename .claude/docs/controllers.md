# Controllers and Method Handlers

How an HTTP surface is declared in this repo, and how the MCP edge serves a JSON-RPC method. The decision records are
ADR-0026 and ADR-0027.

## One surface, one class

Every group of routes is a subclass of `Controller` (`bundlemcp/api/http/`). The subclass names its `prefix` and `tags`,
and marks handler methods with `@route.get`, `@route.post`, `@route.put` or `@route.delete`:

```python
class ServerController(ManagementController):
    prefix = "/servers"
    tags = ("servers",)

    @route.get("")
    async def list_servers(
        self, service: ServerServiceProvider, page: PageProvider
    ) -> Page[ServerRead]:
        ...

    @route.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_server(self, name: str, service: ServerServiceProvider) -> None:
        ...
```

The decorator takes the same keyword options as FastAPI's own (`status_code`, `tags`,
`response_model_exclude_none`, ...). It does not register anything: while the class body runs there is no router and the
method is still unbound. It records the verb, path and options on the method, and constructing the controller binds
every recorded method, bound to the instance, through `APIRouter.add_api_route`. Routes bind in the order they were
written, exactly as module-level decorators do, so a literal path such as `/profiles` is declared before its
parameterised sibling `/{name}`.

Handlers are ordinary bound methods; FastAPI reads their signatures for parameters and their return annotation for the
response model. A handler does HTTP work only: it checks a path-versus-body mismatch, calls **one** service method, and
returns the DTO. Anything it would otherwise compute belongs in the service.

The composition root mounts controllers (`ServerController().mount(app, prefix=API_PREFIX)`); nothing else calls
`include_router`.

## Policy is declared once, on the base

`ManagementController` passes `Depends(ManagementAuth())` as a router-level dependency. Every route of every subclass is
therefore authenticated, and a new route cannot forget it. The same pattern applies to any future shared concern (a
tenant header, a feature gate): put it on a base controller, not on each handler.

Controllers that are deliberately public (`MeController`, `HealthController`, the OAuth controllers,
`McpEndpointController`) derive from `Controller` directly, so the absence of the policy is visible in the class line.

## Where the classes live

| Surface | Package | Base |
|---|---|---|
| Management API | `api/management/controllers/` | `ManagementController` |
| Health probes | `api/health/controllers/` | `Controller` |
| OAuth server, admin login, upstream connect | `api/oauth/controllers/` | `Controller` |
| MCP endpoints | `api/mcp/controllers/` | `Controller` |

Every surface is a package under `api/` with a `controllers/` subpackage; a route class lives there and nowhere else, so
anything outside a `controllers/` folder (`oauth/pages/`, `oauth/browser_state/`, the whole MCP edge machinery) is by
construction not a route.

`bundlemcp/api/http/` holds the base class and the FastAPI providers: glue every delivery package may import. It names
only contracts from `application/`, never an adapter from `infrastructure/`.

## Adding a resource

1. DTOs in `application/schemas/<resource>/`, one class per file, every field described.
2. A repository contract in `application/contracts/persistence/` if the entity is new, with its SQLAlchemy adapter in
   `infrastructure/postgres/` and its fake in `infrastructure/memory/`, both reachable from the `UnitOfWork`.
3. A service in `application/management/`, taking a `UnitOfWork` and the contracts it needs; for a resource addressed by
   name, derive from `NamedResourceService`.
4. A `get_<resource>_service` provider in `api/http/service_providers.py`.
5. A controller in `api/management/controllers/`, registered in `main/app.py`.

## The MCP edge: one class per method

`McpEdge` admits the request (endpoint lookup, authentication, then the client's dialect: per-request `_meta` for a
modern-era client, the session record for a handshake-era one) and hands a `RequestContext` plus a parsed
`JsonRpcMessage` to `MethodRegistry.dispatch`. A handler returns results through `ctx.shape(...)`, so the
revision-specific fields are added in one place (`api/mcp/dialect/`). The registry maps method names to handler
instances:

```python
class PingHandler:
    async def handle(self, ctx: RequestContext, message: JsonRpcMessage) -> Response:
        return rpc_result(message.id, ctx.shape({}))
```

A handler declares its collaborators in its constructor and nothing else. To add a method, write the class and register
it in `McpEdgeAssembly.build()`; the dispatcher does not change. Rate limiting is the `RateLimited` decorator handler,
applied at registration to the methods that count.

`ToolsCallHandler` is the exception in size, not in shape: it resolves the presented tool and hands off to a `ToolCall`
object that carries the call's state through credentials, metering, the upstream call and audit.

## What not to do

- No free route functions on a module-level `APIRouter`.
- No `_auth: ServiceAuthProvider` parameter on individual handlers; the base controller owns it.
- No `if method == "..."` chains; no positional bundles of `(runtime, request, view, record, body)`.
- No reads of `request.app.state.<anything>` outside a `providers` module; a handler asks for a `*Provider` parameter.
