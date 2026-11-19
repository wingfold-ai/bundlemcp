# Design

## Context

CI already runs every gate on every pull request through one `ci-passed` check, the only one the `main` ruleset
requires. This change adds checks around it without touching the required check. Nothing here touches the gateway's
layers; it is all `.github/workflows/`, packaging metadata and docs.

## Decisions

### The weekly run is a schedule on the CI workflow itself

A `schedule` trigger on `ci.yml` re-runs the whole workflow on `main`, so the weekly check is exactly what a push runs.
On a scheduled run the secret scan already falls back to "the history of the checked-out commit", which is the whole
history.

A separate "nightly" workflow would duplicate the jobs and drift from them.

### CodeQL and Scorecard are separate workflows, gated on visibility

Code scanning and Scorecard publishing only work for public repositories on this plan. Each job carries
`if: github.event.repository.visibility == 'public'`, so it is skipped while the repository is private and starts
working the moment it is public, with no follow-up change. Neither is part of `ci-passed`: a new CodeQL alert shows on
the pull request, and becoming a merge blocker is a later decision.

### Provenance from BuildKit, signed by GitHub

`docker/build-push-action` records an SBOM and a `mode=max` provenance record in the registry on every plan.
`actions/attest-build-provenance` adds a signature from GitHub, which `gh attestation verify` checks; it needs a
public repository, so that step carries the same visibility condition. `release.yml` grants the called publish
workflow `id-token: write` and `attestations: write`, because a called workflow cannot widen its caller's permissions.

### Python 3.14 becomes the floor

On Python 3.13 the library fails at import: annotations are evaluated eagerly there, and the code relies on 3.14's
lazy evaluation. Declaring 3.13 was wrong rather than untested, so the floor rises to 3.14. The backend job tests 3.14
and 3.15 and runs the lint steps once, on 3.15. A hermetic test keeps the matrix equal to "floor up to the shipped
version", so raising one without the other fails.

**Alternative:** declare 3.15 only. Rejected: 3.14 works, and the library may be installed outside the image.

### LikeC4 comes from the docs lockfile

The diagrams job runs `npm ci` in `docs/` and calls the locked `likec4`, which Dependabot keeps current. That replaces
`npx --yes likec4`, which fetched the newest release on every run.

## Risks / Trade-offs

- **A weekly run that fails notifies only whoever watches Actions.** That is acceptable for now; the failure is
  visible on the Actions page and on the commit.
- **The second backend job adds about four minutes of runner time** in parallel, not wall time.
- **Images published before this change have no SBOM or attestation.** The deployment guide says so.
