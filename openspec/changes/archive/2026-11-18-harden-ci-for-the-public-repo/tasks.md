# Tasks

## 1. CI workflow

- [x] 1.1 Add a weekly `schedule` to `ci.yml`. Verify that the YAML parses and that the secret-scan step's fallback
  range covers the scheduled event (DEP-10).
- [x] 1.2 Run the backend job as a matrix over Python 3.14 and 3.15, with the lint steps on 3.15 only. Add
  `test_arc2_ci_tests_every_supported_python` and `test_arc2_packages_share_one_python_floor`, and verify that they
  pass (ARC-2).
- [x] 1.3 Give every job in every workflow a `timeout-minutes`. Verify with `grep -c timeout-minutes` against the job
  count (DEP-10).
- [x] 1.4 Validate LikeC4 with the version `docs/package-lock.json` locks. Verify that
  `npx likec4 validate likec4` in `docs/` exits 0.

## 2. Scanning

- [x] 2.1 Add `codeql.yml` (Python, JavaScript/TypeScript, Actions; security-extended), skipped while the repository
  is private. Verify that the YAML parses (DEP-18).
- [x] 2.2 Add `scorecard.yml` and the README badge, skipped while the repository is private. Verify that the YAML
  parses (DEP-19).

## 3. Image provenance

- [x] 3.1 Publish an SBOM and `mode=max` provenance with each image, and attest it in a public repository. Grant the
  permissions in `release.yml`. Verify that the YAML parses (DEP-11).
- [x] 3.2 Document `gh attestation verify` in `docs/self-hosting/deploy.md`. Verify that the docs build passes.

## 4. Python floor

- [x] 4.1 Raise `requires-python` to `>=3.14` in both `pyproject.toml` files, set ruff to `py314`, run `uv lock`, and
  update the stated version in the requirements page, CONTRIBUTING, CLAUDE.md and arc42. Verify that the unit suite
  passes on 3.14 (ARC-2).

## 5. Gates

- [x] 5.1 Run the gates and verify each passes:
  - `uv run pytest -q`, `uv run ruff check .`, `uv run rumdl check .`, `uv run lint-imports`;
  - the four `tools/check_*.py` scripts and `python3 tools/check_spec_ids.py`;
  - `openspec validate --all --strict`.
