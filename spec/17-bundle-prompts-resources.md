# 17 — Bundle-owned prompts and resources

**Status:** Draft · **Origin:** new

## Summary

The same upstream server serves different purposes in different bundles. A Python-execution server can sit in a bundle
for rendering charts and in another for bookkeeping arithmetic. Its tools are identical in both, so what tells the model
how to use them for *this* bundle's purpose is context: worked examples, a house style, the conventions of the domain.
MCP carries that context as **prompts** (reusable message templates the user picks) and **resources** (documents the
client can read into the conversation).

Today a bundle can only pass through the prompts and resources its member servers happen to offer
([BND-8](12-bundles.md)). This spec lets an admin author prompts and resources **on the bundle itself**. They are stored
in Postgres with the bundle and served by the gateway without contacting any upstream, so they cost nothing for an
upstream that scales to zero ([ADR-0043](../docs/adr/0043-contact-upstreams-only-with-a-reason.md)). The bundle's
`description` stays the short always-on `instructions` ([BND-1](12-bundles.md)); prompts and resources hold the longer
material a client pulls in on demand. Rationale and alternatives:
[ADR-0044](../docs/adr/0044-bundle-owned-prompts-and-resources.md).

## Requirements

### Prompts

- **BPR-1** A bundle has zero or more **bundle prompts**. Each has a `name`, an optional `title` and `description`, a
  list of `arguments` (each with `name`, optional `description`, `required` flag, and optional `values` — a closed list
  of suggestions), and an ordered list of `messages`. Natural key: `(bundle, name)`.
- **BPR-2** A bundle prompt's `name` matches `^[a-zA-Z0-9_-]+$` and MUST NOT contain `__`. Member prompts are always
  presented as `<server_name>__<prompt_name>` (BND-8), so an unprefixed name can never collide with one, and a name
  without `__` routes to the bundle without a lookup in any member.
- **BPR-3** A message has a `role` (`user` or `assistant`) and content that is either **text** or a reference to one
  of the same bundle's resources (BPR-6), which `prompts/get` embeds as an MCP embedded resource. Text may contain
  `{{argument}}` placeholders. Substitution is plain text replacement, with no expressions, loops or escapes, and the
  substituted value is inserted verbatim, never re-scanned for placeholders. A write is rejected when a placeholder
  names an undeclared argument or a resource reference names a resource the bundle does not have.
- **BPR-4** `prompts/get` for a bundle prompt rejects a missing required argument with `-32602`, naming it. An
  optional argument that is not supplied is substituted with the empty string.
- **BPR-5** `completion/complete` with a prompt ref to a bundle prompt is answered by the gateway from the argument's
  `values`: case-insensitive prefix match on the partial value, at most 100 results, `hasMore` set when more matched. An
  argument without `values` completes to an empty list. No member is contacted ([PROT-9](32-protocol-passthrough.md)).

### Resources

- **BPR-6** A bundle has zero or more **bundle resources**. Each has a `name` (natural key `(bundle, name)`, matching
  `^[a-zA-Z0-9_-]+(/[a-zA-Z0-9_.-]+)*$` so it can be organised in folders), an optional `title` and `description`, a
  `mime_type`, and text `content`. Accepted MIME types are text only: `text/markdown` (the default), `text/plain`,
  `text/csv`, `application/json` and `application/yaml`. Binary content is out of scope.
- **BPR-7** A bundle resource is presented under the URI `bundle://resources/<name>`. The URI deliberately carries no
  bundle name: a client only ever sees one bundle per endpoint, and a rename of the bundle ([BND-10](12-bundles.md))
  therefore does not change the URIs its prompts and saved conversations refer to. Member resource URIs pass through
  unchanged (BND-8); a member URI in the `bundle:` scheme is shadowed by the bundle and the collision logged.

### Serving

- **BPR-8** Bundle prompts and resources are part of the bundle's cached view, loaded from Postgres with its tools, and
  served without contacting any upstream: `prompts/list`, `prompts/get`, `resources/list`, `resources/read` and
  completions for bundle prompts never open an upstream connection on their behalf.
- **BPR-9** Merging with member passthrough: `prompts/list` and `resources/list` return the bundle's own entries first,
  in name order, then the member entries per BND-8. `prompts/get` with a name without `__` and `resources/read` with a
  `bundle://` URI are answered by the bundle alone; an unknown one is not-found without falling through to the members.
  `resources/templates/list` is unchanged: bundle resources are concrete, never templates.
- **BPR-10** Capability aggregation ([PROT-11](32-protocol-passthrough.md)): the bundle advertises `prompts` when it
  owns at least one prompt or a member advertises prompts, `resources` likewise, and `completions` when a bundle prompt
  argument has `values` or a member advertises completions. An endpoint over a bundle with no member servers at all can
  therefore serve prompts and resources.
- **BPR-11** Change notification: creating, changing or deleting a bundle prompt or resource invalidates the bundle
  ([BND-7](12-bundles.md)). Live clients receive `notifications/prompts/list_changed` or
  `notifications/resources/list_changed` on the stream the client opened for notifications: the GET stream for
  handshake clients, `subscriptions/listen` for modern clients. For modern clients this means the gateway acknowledges
  `promptsListChanged` and `resourcesListChanged` ([PROT-17](32-protocol-passthrough.md)) for changes to bundle-owned
  entries; member changes are still not delivered until upstream pooling lands. `listChanged: true` is advertised for
  prompts and resources whenever the bundle owns any.
- **BPR-12** Cache hints ([PROT-16](32-protocol-passthrough.md)): list results keep the list TTL. `resources/read` of a
  bundle resource is `public` with the same TTL, because its content is identical for every caller.
- **BPR-13** Endpoint profiles ([15-endpoint-profiles.md](15-endpoint-profiles.md)) do not rewrite bundle prompts or
  resources.

### Management

- **BPR-14** Bundle prompts and resources are managed by admins only, through the management API under the bundle —
  `GET`, `PUT` (idempotent upsert by name) and `DELETE` on `/api/v1/bundles/{bundle}/prompts/{name}` and
  `/api/v1/bundles/{bundle}/resources/{name}`, and paginated `GET` on the two collections — and in the admin UI on the
  bundle's detail page. The UI previews a prompt rendered with sample arguments and a resource rendered as Markdown.
- **BPR-15** Bootstrap ([41-bootstrap.md](41-bootstrap.md)) and export/import
  ([42-export-import.md](42-export-import.md)) carry each bundle's prompts and resources inside the bundle entry,
  upserted by natural key. Import keeps EXP-4: an entry absent from the document is not deleted unless `prune=true`.
- **BPR-16** Limits, validated on write: at most 100 prompts and 200 resources per bundle, 64 KiB of message text per
  prompt, 256 KiB per resource, and 4 MiB of resource content per bundle. A write over a limit is rejected with a
  message that names the limit; nothing is truncated.
- **BPR-17** Content is not secret, and the API says so: it is served to every caller of every endpoint of the bundle,
  and to the model. It is logged by size, never by value, like any other configuration write.
- **BPR-18** Reading a bundle prompt or resource over MCP is not audited ([AUD-1](50-audit-log.md) covers tool calls
  only). A management write is logged as a configuration change like the bundle's own writes.
- **BPR-19** The catalogue ([BND-11](12-bundles.md)) lists a bundle's own prompts and resources by title and
  description, so a user sees what context the bundle offers before connecting it.

### Curation of member prompts and resources (optional, separate)

- **BPR-20** *(MAY — independent of BPR-1…19, decided separately)* Member prompts and resources become curatable per
  bundle like tools ([13-tool-management.md](13-tool-management.md)): disable an entry, or override its title and
  description. Curation needs a stored list of what each member offers, so it requires prompt and resource discovery
  ([11-tool-discovery.md](11-tool-discovery.md)), which BND-8 deliberately does not do today. Until then the only way to
  hide a member's prompts in one bundle is to disable the membership.

## Out of scope

- Binary resources, resource templates and resource subscriptions for bundle resources (the content changes only on an
  admin write, which BPR-11 already announces).
- Prompt logic beyond placeholder substitution: conditionals, loops, includes of other prompts.
- Per-endpoint or per-user variants of a bundle's prompts and resources.
- Bundle-owned **tools** (code the gateway would run). Tools stay upstream.

## Open questions

- Whether the URI scheme should be `bundle:` or a less generic, gateway-specific one such as `bundlemcp:`, given that
  clients may show it to users.
- Whether a bundle prompt should be able to embed a **member** resource by URI (fetched live at `prompts/get`), which
  would reintroduce an upstream contact on a path BPR-8 keeps upstream-free.
- Whether management writes need a durable change history (who changed which prompt, when) beyond the configuration log;
  no other configuration entity has one today.
