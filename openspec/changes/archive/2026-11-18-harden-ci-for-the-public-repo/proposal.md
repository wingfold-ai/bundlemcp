# Proposal

## Why

Before the repository goes public, CI should match what people now expect from a security-sensitive open-source
gateway. Today it checks only what a push changes, so a new advisory against an unchanged lockfile goes unnoticed in
a quiet week. Nothing scans the code beyond ruff's rules. The published images carry no provenance anyone can verify.
The packages also declare Python 3.13, which CI never tests and on which the code does not import.

## What Changes

- **Weekly run:** CI runs every week on `main`, besides every pull request and push. On that run the secret scan reads
  the whole history.
- **Python versions:** the backend tests run on every Python version the packages support, 3.14 and 3.15.
  `requires-python` rises to `>=3.14`: the code relies on lazily evaluated annotations, which Python 3.13 lacks.
- **Time limits:** every CI job has a time limit, so a hung job fails instead of running for six hours.
- **Pinned tools:** the LikeC4 validation uses the version the docs lockfile pins, instead of the newest one on npm.
- **Code scanning:** CodeQL scans the Python, TypeScript/Vue and workflow code on every pull request, on `main` and
  weekly, once the repository is public.
- **Scorecard:** OpenSSF Scorecard rates the repository's practices weekly and on every push to `main`, once the
  repository is public. The README shows its badge.
- **Image provenance:** every published image carries an SBOM and a SLSA provenance record. In a public repository it
  also carries a provenance attestation signed by GitHub, which `gh attestation verify` checks. The deployment guide
  says how.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `architecture`: modifies ARC-2 (runtime versions): the Python floor rises to 3.14, and the backend tests run on
  every supported version.
- `deployment`:
  - modifies DEP-10 (CI gates): Python versions, time limits, the weekly run;
  - modifies DEP-11 (image publishing): SBOM and provenance;
  - adds DEP-18 (code scanning) and DEP-19 (repository scorecard).

## Impact

- `.github/workflows/`:
  - `ci.yml`: schedule, Python matrix, time limits, pinned LikeC4;
  - new `codeql.yml` and `scorecard.yml`;
  - `publish.yml` and `release.yml`: SBOM, provenance, attestation;
  - time limits in every other workflow.
- `pyproject.toml` and `packages/bundlemcp/pyproject.toml`: `requires-python = ">=3.14"`. `uv.lock` is re-locked,
  and ruff targets py314.
- Docs:
  - `docs/self-hosting/deploy.md` (verify an image);
  - `docs/self-hosting/requirements.md`, `CONTRIBUTING.md` and `CLAUDE.md` (Python version);
  - the README badge.
- No gateway behaviour changes. No ADR: these are CI and release-process practices, not architectural decisions.
