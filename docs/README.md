# docs/

Two audiences share this folder.

## The documentation site (users and operators)

The Markdown pages in `guide/`, `self-hosting/`, `manage/`, `connect/` and
`integrate/` plus `index.md` are a [VitePress](https://vitepress.dev) site
(spec 61). Run it locally:

```bash
cd docs
npm ci
npm run dev        # http://localhost:5173
npm run build      # static output in .vitepress/dist
```

Navigation lives in `.vitepress/config.ts`; add a page there when you add a
file. Pages describe shipped behaviour only, and change in the same PR as the
behaviour they describe (DOC-5).

## Architecture material (contributors)

| | |
|---|---|
| [arc42/](arc42/README.md) | Architecture rationale, arc42 sections |
| [adr/](adr/README.md) | Architecture decision records, append-only |
| [likec4/](likec4/) | Diagrams as a LikeC4 model (`npx likec4 validate docs/likec4`) |

These are excluded from the site (`srcExclude` in the config): they link
into `spec/` and are read on GitHub.
