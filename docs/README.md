# docs/

Two audiences share this folder.

## The documentation site (users and operators)

The Markdown pages in `guide/`, `self-hosting/`, `manage/`, `connect/` and `integrate/` plus `index.md` are a
[VitePress](https://vitepress.dev) site (the documentation spec). Run it locally:

```bash
# from the repository root
npm run docs:install
npm run docs:dev    # http://localhost:5173
npm run docs:build  # static output in docs/.vitepress/dist

# or inside docs/, as CI runs it
cd docs && npm ci && npm run dev
```

Navigation lives in `.vitepress/config.ts`; add a page there when you add a file. Pages describe shipped behaviour only,
and change in the same PR as the behaviour they describe (DOC-5).

### Publishing

`.github/workflows/publish-docs.yml` builds the site on every push to `main` that touches `docs/` (or when run by hand
from the **Actions** tab) and uploads it by FTP to Infomaniak web hosting (DOC-6). The upload is incremental: the action
keeps `.ftp-deploy-sync-state.json` on the server, sends only changed files, and removes only files it uploaded itself.
The hosting quota is 10 MB, so CI fails any build over 9.6 MB. `public/.htaccess` is copied into the site: it redirects
HTTP to HTTPS and serves `/guide/quickstart` from `guide/quickstart.html`, because the site uses clean URLs.

One-time setup:

1. **Infomaniak Manager** → the web hosting → **FTP / SSH**: create an FTP account and note the hostname. In **Web
   FTP**, check which folder the site is served from. Enable SSL once DNS points at the hosting; Starter has no IPv6, so
   remove any `AAAA` records first.
2. **GitHub → Settings → Secrets and variables → Actions**, repository level:

   | Kind | Name | Value |
   |---|---|---|
   | Secret | `INFOMANIAK_FTP_SERVER` | FTP hostname (or IP) |
   | Secret | `INFOMANIAK_FTP_USERNAME` | FTP account |
   | Secret | `INFOMANIAK_FTP_PASSWORD` | FTP password |
   | Variable | `INFOMANIAK_FTP_SERVER_DIR` | served folder ending in `/` (default `./`) |
   | Variable | `INFOMANIAK_FTP_PROTOCOL` | `ftps` (default), or `ftp` if refused |
   | Variable | `DOCS_PLAUSIBLE_SCRIPT_URL` | optional: Plausible script URL; unset, no analytics are loaded |
   | Variable | `DOCS_REPOSITORY_PUBLIC` | `true` once the source repository is public; otherwise no repository links |
   | Secret | `DOCS_AUTH_USER` | optional: username that the published site asks for |
   | Secret | `DOCS_AUTH_PASSWORD` | optional: its password |

   With both auth secrets set, the next publish puts the site behind a password prompt
   (`.vitepress/basic-auth.htaccess`); delete them and publish again to make it public.

   Until `DOCS_REPOSITORY_PUBLIC` is `true`, the build leaves out every link into the repository: the GitHub icon,
   "Edit this page", the home page's GitHub button, and links in pages and in requirement texts, which keep their
   text. The quickstart, the home page and the deployment page show a `<RepositoryNotice />` instead.
   `tools/check_docs_repository_links.py` checks both builds in CI. Set the variable and publish again to show them.

   The site's address is `https://bundlemcp.dev`. The hosting also serves `bundlemcp.com` and both `www` names, and
   `public/.htaccess` redirects each of them, with the path, to `https://bundlemcp.dev` (301).

   The build also writes `sitemap.xml`, listing every page under `https://bundlemcp.dev`, and `public/robots.txt`
   points crawlers to it; `tools/check_docs_sitemap.py` checks both in CI. Each page's date, on the page and in the
   sitemap, is the last commit that changed it, which is why the publish workflow checks out the full history.
The build also writes `llms.txt`, every sidebar page with its title, URL and description for AI assistants, and
`llms-full.txt`, the Markdown of the same pages. Each page's `description` frontmatter is its search-result snippet,
`og:description` and `llms.txt` line, so a new page needs one, at most 160 characters.

## Brand assets

`public/` holds the logo files the site and the repository README use. The bundle mark (`logo-mark.svg`, `logo.svg`) is
hand-drawn; the wordmark files (`wordmark-*.svg`, `lockup-*.svg`, `banner.svg`) are generated from
`brand/logo-text.html`, the wordmark's HTML source, by tracing the Roboto outlines so they render without a web font:

```bash
uv run --with fonttools python docs/brand/build_logo_text.py
```

Edit the HTML, re-run the script, commit both.

`public/og-image.png` is the link-preview image (1200×630) that every page's Open Graph and Twitter card tags point to,
so a shared link shows the logo, the headline and the servers-to-bundle diagram. It is rendered from
`.vitepress/og-image/og.html`, which uses the logo files above:

```bash
uv run --no-project --with playwright tools/render_og_image.py
```

Commit the HTML and the PNG together. LinkedIn caches a preview for days; after a change, refresh it once with
LinkedIn's Post Inspector.

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

These are excluded from the site (`srcExclude` in the config): they link into `openspec/` and are read on GitHub.
