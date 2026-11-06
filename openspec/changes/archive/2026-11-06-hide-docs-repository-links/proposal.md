# Proposal

## Why

The documentation site goes public before the source repository does. Until then every link into the repository
(the GitHub icon, "Edit this page" on every page, the home page's GitHub button, links to the changelog, issues and
specifications) reaches GitHub's 404, and the quickstart and deployment commands cannot work for a visitor, since
`git clone` and the container images need the repository.

## What Changes

- A build setting, the repository variable `DOCS_REPOSITORY_PUBLIC`, says whether the repository is public. Unless it
  is `true`, the site is built without any link into the repository: no GitHub icon, no edit links, no GitHub button,
  no footer line pointing at the repository, and links in pages and requirement texts become their plain text.
- While the repository is private, the home page, the quickstart and the deployment page show a notice that the
  source and images are being prepared for public release.
- Setting the variable to `true` and publishing again brings every link back and removes the notice.
- CI builds the site with the same setting as the publish workflow and checks that the output matches it.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `documentation`: adds DOC-14 (repository links follow the repository's visibility).

## Impact

- `docs/.vitepress/config.ts`, a new `docs/.vitepress/repository-links.ts`, the theme (`RepositoryNotice.vue`,
  `RequirementsTable.vue`) and three pages that show the notice.
- `.github/workflows/ci.yml` and `publish-docs.yml` pass the variable to the build; a new
  `tools/check_docs_repository_links.py` checks the result.
- `docs/README.md` documents the variable.
- No gateway code, DTO or route changes; no ADR.
