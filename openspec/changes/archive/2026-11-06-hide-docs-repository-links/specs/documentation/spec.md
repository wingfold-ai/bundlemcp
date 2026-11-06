# Spec Delta

## ADDED Requirements

### Requirement: DOC-14 Repository links follow its visibility
The documentation site MUST link into the source repository only when it is built with the repository declared
public (`DOCS_REPOSITORY_PUBLIC=true`, a repository variable the publish workflow passes to the build). Built
otherwise, the site carries no link into the repository: no GitHub icon, no "Edit this page" link, no home-page
button and no repository line in the footer; a link into the repository in a page or in a requirement's text keeps
its text and loses the link. The home page, the quickstart and the deployment page then say that the source code and
container images are not public yet. CI builds the site with the same setting as the publish workflow and checks the
output against it.

#### Scenario: A private build has no repository links
- **WHEN** the site is built without `DOCS_REPOSITORY_PUBLIC=true`
- **THEN** no built page and no requirement text links to the repository, and the home page, the quickstart and the
  deployment page show the not-public notice

#### Scenario: A public build links to the repository
- **WHEN** the site is built with `DOCS_REPOSITORY_PUBLIC=true`
- **THEN** the GitHub icon, the edit links and the links in pages are present, and no page shows the not-public
  notice

#### Scenario: A repository link in a private build fails CI
- **WHEN** a built page or requirement text links to the repository while the setting is not `true`
- **THEN** the CI `docs` job fails and names the file
