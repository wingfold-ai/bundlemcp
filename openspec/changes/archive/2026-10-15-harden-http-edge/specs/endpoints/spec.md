## MODIFIED Requirements

### Requirement: EP-9 Request size limit
`POST /{endpoint_name}/mcp` MUST reject a request body larger than the request limit
([SEC-7](../security/spec.md), runtime-configurable, default 4 MiB) with `413 Payload Too Large` and a
JSON-RPC error body, before the body is parsed or any database work is done — whether the size is declared in
`Content-Length` or only becomes apparent while a chunked body streams in. CORS on the route follows
[SEC-5](../security/spec.md).

#### Scenario: Oversized request is rejected early
- **WHEN** a client posts to `/main/mcp` with `Content-Length` greater than the request limit
- **THEN** the gateway answers 413 without authenticating the caller

#### Scenario: Oversized chunked request is rejected
- **WHEN** a client posts a chunked body to `/main/mcp` that exceeds the request limit
- **THEN** the gateway answers 413 without authenticating the caller or parsing the body
