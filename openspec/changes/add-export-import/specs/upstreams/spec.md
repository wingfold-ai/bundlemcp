## MODIFIED Requirements

### Requirement: UPS-16 Published name
The resource MUST be called an **upstream server**, or **upstream** for short, everywhere a person or a client of the
gateway reads it. On the wire it is always the short form: the management API collection is `/api/v1/upstreams` (with
every sub-route and action of the former `/api/v1/servers` under it), a bundle's members are
`/api/v1/bundles/{name}/upstreams`, the OpenAPI tag is `upstreams`, the bootstrap and export documents use the key
`upstreams` ([MGMT-15](../../../../specs/management/spec.md), [MGMT-17](../management/spec.md)), the admin UI routes are
`/upstreams` and its navigation and list page say *Upstream servers*, and the documentation introduces the term as
"upstream server (upstream for short)" and may use either afterwards. "Server" alone is ambiguous next to the gateway,
which is itself an MCP server to its clients and an HTTP server to everyone. Field names inside payloads
(`server_name`, `server_id`, the metering context's `server`) are unchanged: each is already qualified by the object it
sits on, and the metering hook contract is versioned separately ([PROT-26](../../../../specs/protocol/spec.md)). The
old names are not kept as aliases: `/api/v1/servers` answers `404` and a bootstrap or import document using `servers`
is rejected ([ADR-0045](../../../../../docs/adr/0045-upstreams-on-the-published-surface.md)).

#### Scenario: The former paths are gone
- **WHEN** `GET /api/v1/servers/weather` or `GET /api/v1/bundles/b1/servers` is requested
- **THEN** the response is `404`

#### Scenario: OpenAPI uses the short form
- **WHEN** the OpenAPI document is read
- **THEN** it has the tag `upstreams` and no tag `servers`

#### Scenario: An old bootstrap document is rejected
- **WHEN** a bootstrap document uses the top-level key `servers`
- **THEN** it is rejected with a validation error rather than misread

#### Scenario: The export uses the short form
- **WHEN** `GET /api/v1/export` is called
- **THEN** the document lists upstream servers under the key `upstreams` and has no key `servers`
