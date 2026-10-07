# docs/

Two audiences share this folder.

## The documentation site (users and operators)

The Markdown pages in `guide/`, `self-hosting/`, `manage/`, `connect/` and `integrate/` plus `index.md` are a
[VitePress](https://vitepress.dev) site (spec 61). Run it locally:

```bash
# from the repository root
pnpm docs:install
pnpm docs:dev        # http://localhost:5173
pnpm docs:build      # static output in docs/.vitepress/dist

# or inside docs/ with npm, which is what CI uses
cd docs && npm ci && npm run dev
```

Navigation lives in `.vitepress/config.ts`; add a page there when you add a file. Pages describe shipped behaviour only,
and change in the same PR as the behaviour they describe (DOC-5).

## Brand assets

`public/` holds the logo files the site and the repository README use. The bundle mark (`logo-mark.svg`, `logo.svg`) is
hand-drawn; the wordmark files (`wordmark-*.svg`, `lockup-*.svg`, `banner.svg`) are generated from
`brand/logo-text.html`, the wordmark's HTML source, by tracing the Roboto outlines so they render without a web font:

```bash
uv run --with fonttools python docs/brand/build_logo_text.py
```

Edit the HTML, re-run the script, commit both.

## Diagrams

The context and deployment diagrams in the guides are live views of the LikeC4 model in `likec4/`. `npm run build` and
`npm run dev` first run `likec4 codegen webcomponent`, which compiles every view into `public/likec4-views.js` (ignored
by git); the `LikeC4Diagram` component in `.vitepress/theme/` loads that bundle on demand and renders `<likec4-view>`,
with pan, zoom, click-through navigation and a fullscreen browser. Edit the model, and the next build picks it up.

## Architecture material (contributors)

| | |
|---|---|
| [arc42/](arc42/README.md) | Architecture rationale, arc42 sections |
| [adr/](adr/README.md) | Architecture decision records, append-only |
| [likec4/](likec4/) | Diagrams as a LikeC4 model (`npx likec4 validate docs/likec4`) |

These are excluded from the site (`srcExclude` in the config): they link into `spec/` and are read on GitHub.
