## ADDED Requirements

### Requirement: BND-5 Self-reference guard
A bundle MUST NOT include bundlemcp's own endpoints as member servers (self/circular reference guard). Adding an
upstream as a member SHALL be refused with `409` when its URL has the origin of the gateway's public URL (host compared
case-insensitively, default port implied, trailing slash ignored) and a path `/{name}/mcp` directly under the public
URL's path, for any `name`, so an endpoint created later is covered too. Changing the URL of an upstream that is a
member of any bundle SHALL be refused the same way.

#### Scenario: Own endpoint is refused as a member
- **GIVEN** the public URL is `https://gw.example.com` and upstream `loop` has URL `https://gw.example.com/loop-ep/mcp`
- **WHEN** `PUT /api/v1/bundles/b1/upstreams/loop` is called
- **THEN** the response is `409`, the error names the self-reference, and no membership is stored

#### Scenario: Spelling variants are recognised
- **GIVEN** the public URL is `https://gw.example.com`
- **WHEN** an upstream with URL `https://GW.Example.com:443/loop-ep/mcp/` is added to a bundle
- **THEN** the membership is refused with `409`

#### Scenario: A name that is not yet an endpoint is still refused
- **GIVEN** no endpoint named `later` exists
- **WHEN** an upstream with URL `https://gw.example.com/later/mcp` is added to a bundle
- **THEN** the membership is refused with `409`

#### Scenario: Changing a member's URL to the gateway is refused
- **GIVEN** upstream `weather` is a member of bundle `b1`
- **WHEN** `PUT /api/v1/upstreams/weather` changes its URL to `https://gw.example.com/b1-ep/mcp`
- **THEN** the response is `409` and the stored URL is unchanged

#### Scenario: Other paths and hosts on the same domain are allowed
- **WHEN** an upstream with URL `https://gw.example.com/tools/weather/mcp` or `https://api.example.com/loop-ep/mcp` is
  added to a bundle
- **THEN** the membership is stored

#### Scenario: A non-member upstream may point anywhere
- **WHEN** an upstream that belongs to no bundle is registered with URL `https://gw.example.com/loop-ep/mcp`
- **THEN** the registration succeeds; the guard applies only once it would become, or already is, a member
