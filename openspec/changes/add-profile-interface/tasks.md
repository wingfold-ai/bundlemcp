# Tasks

## 1. Decide EP-13 and BND-13

- [ ] 1.1 Record the maintainers' choice (build the stage or amend the wording), taken together with PROT-25 in
  align-metering-contract; on "amend", replace the EP-13 and BND-13 deltas with the amended wording and drop group 3;
  verify with `openspec validate add-profile-interface --strict`

## 2. Profile interface and catalogue (EP-14)

- [ ] 2.1 Add `domain/endpoints/profiles/` with the `EndpointProfilePreset` protocol, the three presets and
  `ProfileCatalog`; verify with domain tests `test_prof5_catalog_matches_enum` and per-preset
  `test_prof6_*_auth_rule` cases
- [ ] 2.2 Make `EndpointUpsert.auth_and_profile_rules` delegate the profile rule to the catalogue; verify the existing
  EP-15 API tests pass unchanged
- [ ] 2.3 Move the profile list into `ProfileService` behind a provider and make the controller call it; verify the
  existing EP-14 listing test and `cd apps/web && npm run openapi` (no diff expected)
- [ ] 2.4 Add `test_prof5_registered_profile_used_everywhere` with a test-only preset registered in a catalogue built
  for the test app; verify it covers listing, write validation and tool transform

## 3. Tool pipeline (EP-13, BND-13)

- [ ] 3.1 Add `domain/bundles/tool_pipeline.py` with `ToolStage`, `CurationFilter`, `ProfileStage` and
  `OverrideStage`, and make `bundle_view_loader.py` run it; verify with `test_prof4_stage_order` and the existing
  BND-13, BND-15 and EP-12 tests unchanged
- [ ] 3.2 Add `test_prof4_profile_drop_rejected_on_call` and `test_tm2_disabled_tool_never_reaches_profile` through
  the ASGI app; verify both pass and no upstream is contacted
- [ ] 3.3 Remove `profile_annotations` and the name branch from `tool_presentation.py`; verify with
  `grep -rn "EndpointProfile.CHATGPT" packages/bundlemcp/bundlemcp` returning only the catalogue

## 4. Documentation

- [ ] 4.1 Write the ADR (next free number) for profiles as a registered interface and the tool pipeline as ordered
  stages, add it to `docs/adr/README.md`; verify with `python3 tools/check_adr_graph.py`
- [ ] 4.2 Update `docs/manage/endpoints.md` (how profiles work) and the arc42 building-block view for the new domain
  package, and the LikeC4 model if it names the presentation module; verify with `python3 tools/check_docs_symbols.py`
  and `npx likec4 validate docs/likec4`

## 5. Gates

- [ ] 5.1 Run `uv run pytest -q`, `uv run ruff check .`, `uv run rumdl check .` and `uv run lint-imports`; verify all
  pass with no new exceptions
- [ ] 5.2 Run `python3 tools/check_docs_links.py`, `check_docs_symbols.py`, `check_docs_settings.py` and
  `check_adr_graph.py`; verify all pass
- [ ] 5.3 Run `cd apps/web && npm run openapi`; verify `apps/web/openapi.json` and `apps/web/types/api.d.ts` are
  unchanged or committed
- [ ] 5.4 Run `openspec validate --all --strict`; verify it passes
