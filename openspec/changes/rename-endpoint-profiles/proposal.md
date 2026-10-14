# Proposal

## Why

Two of the three endpoint profiles are named after the client they were first built for, `claude` and `chatgpt`, not
after what they do. A name like that says nothing about the effect. `claude` changes no tool; it only requires
OAuth. `chatgpt` rewrites every tool's annotations. Neither is specific to its namesake: an OAuth-only endpoint suits
any client that signs a person in, and the rewrite suits any client that is wary of write tools. The names also date
badly. If ChatGPT stops needing the rewrite, or a second client needs it, the `chatgpt` profile ends up doing the wrong
thing for its name. Renaming the profiles for what they change follows the repo's rule of naming things for their
mechanism, not for a moment in time.

## What Changes

- **BREAKING** The `claude` profile is renamed `oauth_only`. Its behaviour is unchanged: the endpoint must use exactly
  `auth_modes: [oauth]`, and tools pass through untransformed.
- **BREAKING** The `chatgpt` profile is renamed `write_as_read`. Its behaviour is unchanged: every served tool is
  presented with `readOnlyHint: true` and `destructiveHint: false`, the tools still perform their real operations,
  explicit per-tool overrides still win, and the endpoint needs `oauth` or `api_key`.
- `default` keeps its name.
- **BREAKING** This is a hard rename with no aliases. The management API, the profile listing and bootstrap files use
  only the new identifiers. A request or bootstrap file that names `claude` or `chatgpt` is rejected with a validation
  error that lists the allowed profiles.
- A database migration rewrites the profile stored on existing endpoints (`claude` → `oauth_only`,
  `chatgpt` → `write_as_read`), so existing endpoints keep serving after an upgrade without an admin doing anything.
  Downgrading reverses it.
- The profile descriptions the API publishes say what each profile changes, not which client it is for. The admin UI's
  per-client setup steps still recommend a client for each profile: `oauth_only` for claude.ai, `write_as_read` for
  ChatGPT. Clients are now recommended uses, not identities.
- The demo seed keeps its endpoints named `claude` and `chatgpt`, since endpoint names are the admin's choice. They now
  use the `oauth_only` and `write_as_read` profiles.
- The docs (core concepts, manage/endpoints, connect/claude, connect/chatgpt, quickstart, bootstrap, glossary) use the
  new names and keep saying which profile to pick for claude.ai and ChatGPT.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `endpoints`: renames EP-11 and EP-12 and modifies them, with EP-4, EP-14 and EP-15, to name the profiles `oauth_only`
  and `write_as_read`. Adds EP-23: profile identifiers name what the profile changes, and an endpoint stored under a
  former identifier is migrated.
- `bundles`: modifies BND-13, BND-15 and BND-30, whose scenarios name the `chatgpt` profile.
- `admin-ui`: modifies UI-1, which names the chatgpt-profile warning.
- `documentation`: modifies DOC-2, which describes connect/claude.md and connect/chatgpt.md in terms of the old
  profiles.

## Impact

- **API (breaking):** `EndpointUpsert.profile`, `EndpointRead.profile`, `AvailableEndpointRead.profile` and the profile
  listing take the new enum values. This regenerates `apps/web/openapi.json` and `apps/web/types/api.d.ts`.
- **Metering hook:** today the hook's context does not carry the profile. The open `align-metering-contract` change
  adds it, so that change has to use the new identifiers.
- **Bootstrap files (breaking):** a file naming `profile: claude` or `profile: chatgpt` fails validation at start-up
  and has to be edited. `deploy/seed.yaml` is updated in this change.
- **Database:** a new Alembic revision (0009) rewrites `endpoints.profile`. The column is a plain string, so no type
  changes.
- **Code:** the `EndpointProfile` enum, the two preset classes and their modules, the profile catalogue, the web UI
  pages that check for the `chatgpt` profile (`bundles/[name].vue`, `endpoints/[name].vue`, `catalogue/[bundle].vue`),
  and the tests that use the old identifiers.
- **Open changes:** `align-metering-contract`, `complete-admin-ui` and `add-inspector` name the old profiles in their
  delta specs or tasks. Their text is updated to the new identifiers so they don't bring the old names back.
- **Spec notes:** the entity list under *Entities* in the architecture spec and the *Docs and onboarding* note in the
  documentation spec name the old identifiers. Neither is a requirement, so they are edited in place once the rename is
  implemented.
- **ADR:** adds ADR-0047 "Profiles are named for what they change", which amends ADR-0007. ADR-0007's decision
  enumerates the old identifiers.
- No GitHub issue. The change comes from review feedback on the docs.
