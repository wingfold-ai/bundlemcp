# Design

## Context

The site is VitePress. Repository links come from four places: the theme config (GitHub icon, edit links, footer),
the home page's frontmatter (hero button), Markdown links in pages, and the requirements ledger, whose texts
`tools/spec_ledger.py` rewrites to repository URLs and which is rendered with the site's own Markdown renderer.
The Requirements page adds "specification", "source" and change links in its Vue component. Nothing here touches the
gateway's layers.

## Goals / Non-Goals

**Goals:** a public site with no dead repository links while the repository is private, switched back by one setting.

**Non-Goals:** rewriting the quickstart for visitors without the repository; publishing the images; hiding the
`git clone` commands, which the notice explains instead.

## Decisions

- **Off unless declared public.** The variable must say `true` for links to appear, so a forgotten setting fails safe
  (no dead links) and nothing in the repository settings has to change before the repository goes public. The
  alternative, a `DOCS_REPOSITORY_PRIVATE` switch like the password secrets, would publish dead links if unset.
- **One Markdown rule for pages and requirement texts.** A core rule removes `link_open`/`link_close` pairs whose
  href is the repository or under it, and keeps their content. The ledger renders with the site's Markdown config,
  so the same rule covers it. Alternative: wrap each link in a component. Rejected: every future link would need it.
- **Frontmatter and theme config in `config.ts`.** `transformPageData` filters the hero actions; the icon, edit link
  and footer line are conditional. The component reads `repositoryPublic` from the theme config, since a client
  bundle cannot read the build's environment.
- **A notice component on the three pages whose commands need the repository**, rendering nothing in a public build.
- **`tools/check_docs_repository_links.py`** runs after the build in CI and before the upload in the publish
  workflow, with the same variable: private builds must carry no repository href (pages and `requirements.json`)
  and must show the notice on the three pages; public builds must carry links and no notice.

## Risks / Trade-offs

- [The `git clone` commands stay visible] → The notice above them says why they do not work yet; hiding them would
  leave the quickstart empty.
- [CI on a pull request tests only the mode the variable selects] → The check's hermetic tests cover both modes, and
  the local verification builds both.
