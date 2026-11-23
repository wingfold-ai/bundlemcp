# Tasks

## 1. Only user-facing changes release

- [x] 1.1 Add the non-releasing scopes `ci`, `repo` and `docs` to `tools/pull_request_release.py`, so the derived
  bump is `none` for them whatever the type and `!`. Extend the parametrised cases of
  `test_dep12_title_derives_type_and_semver_labels` with `fix(ci): …` → `semver: none`, `refactor(repo)!: …` →
  `semver: none` and `fix: …` → `semver: patch`, and verify that they pass (DEP-12).
- [x] 1.2 Add `test_dep12_a_non_releasing_scope_gets_no_entry_or_bump`, which runs `apply` for a `fix(ci)` title and
  checks that `CHANGELOG.md` and the version files are unchanged. Verify that it passes (DEP-12).
- [x] 1.3 In `CONTRIBUTING.md`, in "Commit and pull request titles" and in "How a release happens", say that the
  scopes `ci`, `repo` and `docs` release nothing and when to use them. Verify that `uv run rumdl check .` is clean.

## 2. Every release page explains itself

- [x] 2.1 Make `tools/release_notes.py` read the protocol source at the given tag through `git show`, and the
  changelog as it stands, so a later correction reaches a refreshed release. Add
  `test_dep11_notes_take_the_current_entry_and_the_protocol_the_tag_shipped` on a temporary git repository with two
  tags, and verify that it passes (DEP-11).
- [x] 2.2 Add the frame to `notes()`: the project sentence, the entry, both image references, the preview caveat
  below `1.0.0`, the Quickstart, Documentation and Discussions links, the *Full Changelog* compare link (omitted
  without a previous tag), and the protocol line last. Add a `--repo owner/name` argument with the default
  `wingfold-ai/bundlemcp`. Add `test_dep11_notes_frame_the_entry`, `test_dep11_preview_caveat_only_below_1_0` and
  `test_dep11_first_release_has_no_compare_link`. Keep the existing protocol tests passing (DEP-11).
- [x] 2.3 Add `--latest` to `tools/release_notes.py`. It prints `true` only when the tag is the highest `v*.*.*` tag.
  Add `test_dep11_only_the_highest_version_is_latest` for `v1.1.1` beside `v1.2.0`, and for `v1.2.0` itself. Verify
  that it passes (DEP-11).
- [x] 2.4 In `.github/workflows/release.yml`, pass `--repo "$GITHUB_REPOSITORY"` to the notes call, and add
  `--latest="$(python3 tools/release_notes.py --latest "$TAG")"` to `gh release create`. Update the comment at the
  top of the file. Verify that the YAML parses and that the `release` job's script runs locally against `v0.4.2`
  with `gh` replaced by `echo`.
- [x] 2.5 Describe the release page in CONTRIBUTING.md's "How a release happens" (what the notes contain and when a
  release is marked latest). Verify that `python3 tools/check_docs_links.py` passes.

## 3. Refresh the published v0.4 releases

- [x] 3.1 Generate the notes for v0.4.0, v0.4.1 and v0.4.2 with the new script into the scratchpad, and show them to
  the maintainer. Do not edit any release before the maintainer approves.
- [x] 3.2 After approval, run `gh release edit <tag> --notes-file <file>` for each of the three tags. Verify with
  `gh release view <tag>` that each body matches its file, and that `releases/latest` still leads to v0.4.2.

## 4. Gates

- [x] 4.1 Run `uv run pytest -q`, `uv run ruff check .`, `uv run rumdl check .` and `uv run lint-imports`, and the
  documentation checks `python3 tools/check_docs_links.py`, `check_docs_symbols.py`, `check_docs_settings.py` and
  `check_adr_graph.py`. Also run `python3 tools/check_spec_ids.py` and `openspec validate --all --strict`. All must
  pass. No DTO or route changes, so `npm run openapi` is not needed.
