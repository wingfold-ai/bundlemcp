## ADDED Requirements

### Requirement: UPS-24 Prompt and resource discovery
When a discovery probe reaches a server whose capability snapshot ([UPS-22](../../../../specs/upstreams/spec.md))
advertises `prompts` or `resources`, the gateway SHALL also list them and cache, per entry, the prompt name or
resource URI with its title and description — never prompt messages or resource content — hash-gated like tools
(UPS-18) and kept, not deleted, when they vanish (UPS-19). The number of cached entries per server and kind is bounded;
a longer listing is cached truncated and the truncation is logged. The cache feeds curation
([BND-37](../bundles/spec.md)) only; endpoints keep serving these lists live.

#### Scenario: Prompts are cached at discovery
- **WHEN** discovery succeeds against an upstream advertising `prompts` that lists prompts `daily` and `weekly`
- **THEN** both prompts are cached for the server with their titles and descriptions, and no prompt messages are stored

#### Scenario: A server without the capability is not asked
- **WHEN** discovery succeeds against an upstream whose snapshot does not advertise `resources`
- **THEN** the upstream receives no `resources/list` request

#### Scenario: A failed listing keeps the cache
- **WHEN** a later discovery of the same server fails before or while listing its prompts
- **THEN** the cached prompts are unchanged

#### Scenario: A long resource listing is truncated observably
- **WHEN** an upstream lists more resources than the bound
- **THEN** only the bound is cached and a warning naming the server is logged
