# Spec Delta

## ADDED Requirements

### Requirement: DOC-22 A blog with an RSS feed
The documentation site MUST publish a blog at `/blog/`, linked as "Blog" in its top navigation, directly before
"Roadmap". A post is a Markdown page `docs/blog/<slug>.md`, published at `/blog/<slug>`, whose frontmatter declares
`title`, `description`, `date` as `YYYY-MM-DD` and `author`, a name the site knows a profile link for; `draft: true`
marks a draft. A post with a field missing, a malformed date or an unknown author fails the build.

- **Index:** `/blog/` lists every published post, newest first, each with its date, its title linking the post, and
  its description. The list is built from the posts themselves. With no published post, the index says so in one
  sentence and lists nothing.
- **Post page:** shows the post's title, its date, an author line with the author's name linking their profile, and a
  link back to `/blog/`. No page of the blog shows the sidebar.
- **Feed:** the build writes an RSS 2.0 feed to `/blog/feed.xml` with one item per published post, newest first, each
  with the post's title, `https://bundlemcp.dev` URL, description, date and author. Every page's head announces the
  feed with `<link rel="alternate" type="application/rss+xml">`.
- **Drafts:** a production build leaves a draft out entirely: no page is built for it, and the index, the feed, the
  sitemap ([DOC-13](spec.md)) and `llms.txt` ([DOC-21](spec.md)) do not name it. The local development server still
  renders it, marked as a draft.
- **Discovery:** a published post is a page of the site like any other. It is in the sitemap, its description
  ([DOC-20](spec.md)) and link preview tags ([DOC-19](spec.md)) are its own, with `og:type` `article` and its
  publication date, and `llms.txt` lists it under a `## Blog` section, newest first, with `llms-full.txt` holding its
  Markdown.

#### Scenario: The index lists a published post
- **GIVEN** a post `docs/blog/hello.md` dated 2026-11-24, not a draft
- **WHEN** the site is built
- **THEN** `/blog/` lists it with that date, its title linking `/blog/hello` and its description, and the post page
  shows the author line and a link back to `/blog/`

#### Scenario: The feed, sitemap and llms.txt name a published post
- **GIVEN** the same post
- **WHEN** the site is built
- **THEN** `/blog/feed.xml` is an RSS 2.0 document with an item linking `https://bundlemcp.dev/blog/hello`, the sitemap
  lists that URL, and `llms.txt` lists it under `## Blog`

#### Scenario: A draft leaves no trace in production
- **GIVEN** the same post with `draft: true`
- **WHEN** the site is built for production
- **THEN** no page `/blog/hello` is built, and neither the index, the feed, the sitemap nor `llms.txt` names it

#### Scenario: An empty blog says so
- **GIVEN** no published post
- **WHEN** `/blog/` is fetched from the built site
- **THEN** it shows one sentence saying there are no posts yet, and the feed holds no item

#### Scenario: Readers find the feed
- **WHEN** any page of the built site is fetched
- **THEN** its head holds `<link rel="alternate" type="application/rss+xml" href="https://bundlemcp.dev/blog/feed.xml">`

#### Scenario: A post without a date fails the build
- **WHEN** a non-draft post has no `date`, or one not of the form `YYYY-MM-DD`
- **THEN** the build fails and names the post
