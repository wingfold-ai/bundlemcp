# Design

## Context

A profile's identifier is the `EndpointProfile` enum value (domain). It is stored as a plain string in
`endpoints.profile` (infrastructure/postgres, migration 0001), and the `schemas/` DTOs (`EndpointUpsert`,
`EndpointRead`, `AvailableEndpointRead`, `EndpointProfileRead`) publish it to the OpenAPI document and the generated TS
types. Each preset class (`ClaudeProfile`, `ChatgptProfile` in `domain/endpoints/profiles/`) sets its `name` to its
enum member, and `ProfileCatalog` refuses to build unless every member has a preset registered under its own name. The
bootstrap runner validates endpoint documents against the same enum. Three web pages compare against the string
`"chatgpt"`: the bundle and endpoint pages to decide whether to show the warning, and the catalogue to pick the
setup steps for each client.

## Goals / Non-Goals

**Goals:**

- One set of identifiers end to end: enum, stored rows, API, bootstrap, UI, docs.
- An upgrade that needs no admin action: stored endpoints keep serving.
- The web UI no longer compares profile names to decide whether to show the warning.

**Non-Goals:**

- No change to what any profile does: its constraint, its transform and its warning text stay as they are.
- No aliases or a deprecation window for the old identifiers (see the proposal).
- Renaming the demo seed's endpoints (`claude`, `chatgpt`). Those are endpoint names, which the admin chooses, and the
  quickstart and connect pages use them as URLs.
- Renaming scenario titles in the main specs. A MODIFIED requirement has to keep every scenario title the current spec
  has, so the old titles (`claude endpoint without oauth is rejected`, …) stay. Their bodies use the new identifiers.

## Decisions

**Enum members follow the values.** `EndpointProfile.OAUTH_ONLY = "oauth_only"` and
`EndpointProfile.WRITE_AS_READ = "write_as_read"` (domain). The presets become `OauthOnlyProfile` in
`oauth_only_profile.py` and `WriteAsReadProfile` in `write_as_read_profile.py`, so a class is named for what it does
like its identifier. The alternative, keeping the class names and changing only the values, would leave exactly the
client names this change removes.

**Descriptions say what changes, not who it is for.** `OauthOnlyProfile.description` becomes "OAuth sign-in only;
tools pass through unchanged". `WriteAsReadProfile.description` keeps its current text, which already describes the
effect. The rule-violation messages name the new identifier (`"oauth_only profile requires auth_modes == ['oauth']
(EP-15)"`). These descriptions are published through the profile listing, so they reach the admin UI unchanged.

**The rows are migrated with a data-only Alembic revision.** Revision `0009` (infrastructure/postgres) runs two
`UPDATE endpoints SET profile = … WHERE profile = …` statements, and `downgrade()` reverses them. The column is a
`String`, so no type changes. Doing this in SQL, rather than mapping old values when rows are read, keeps the domain
free of the former names. Once the migration has run, nothing in the code knows them.

**The warning is data-driven in the UI.** `bundles/[name].vue` and `endpoints/[name].vue` show the warning whenever
the selected profile's entry in the profile listing has a `warning`, instead of when the name equals `"chatgpt"`. This
removes the only branch on a profile's name outside the catalogue that EP-14 forbids. It also means a future profile
that carries a warning shows it without a UI change.

**Recommending a client stays in the UI.** The catalogue's setup steps are written per client (claude.ai menus, ChatGPT
menus), and which client a profile suits is advice, not behaviour. The `switch` in `catalogue/[bundle].vue` and its
`CLIENT_LABEL` map are re-keyed to `oauth_only` → claude.ai and `write_as_read` → ChatGPT. Considered instead: a
`recommended_client` field on each preset. That would put client names back into the domain, which is what this
change removes, so it is rejected.

**The ADR amends ADR-0007.** ADR-0007's decision enumerates `claude` and `chatgpt`. ADR-0047 records the naming rule
(an identifier names its effect) and the hard-rename choice. ADR-0007 gets an "Amended by" link, and its body is left
unchanged because ADRs are append-only.

## Risks / Trade-offs

- [A bootstrap file or script that names `claude`/`chatgpt` breaks on upgrade] → The validation error lists the
  accepted values. The docs page on bootstrap files and the upgrade note in the deploy guide name the
  mapping.
- [Revision 0009 breaks the convention in the deploy guide that migrations stay backward-compatible one release
  back. During a rolling update, an old replica reads a row the migration already rewrote, fails to validate
  `oauth_only` and errors on that endpoint until it is replaced] → Accepted deliberately: there are no versioned
  releases or outside deployments yet, and a two-step rename would keep the old identifiers in the row mapping for a
  release. The migration's docstring says so, and `docs/self-hosting/deploy.md` (Migrations and upgrades) gets a note
  for this upgrade: stop the old replicas before starting the new ones.
- [The application layer or other callers branch on `"chatgpt"`] → Called out as BREAKING in the proposal and in the
  commit message. The open `align-metering-contract` change is updated before it lands, so the metering context never
  ships the old value.
- [Old scenario titles in the main spec still say `claude`/`chatgpt`] → This is what the validator requires, and the
  bodies are correct. A later change can replace those scenarios with REMOVED + ADDED if the titles matter.

## Migration Plan

1. Stop every gateway replica, then deploy the new version. The image runs `alembic upgrade head` before it serves, so
   revision `0009` rewrites the stored profiles before any new replica answers.
2. Update any bootstrap file or script that names `claude` or `chatgpt`.
3. Rollback: `alembic downgrade 0008` restores the old identifiers, and then the previous version can be deployed.
