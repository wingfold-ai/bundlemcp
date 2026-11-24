#!/usr/bin/env python3
"""Check that the built documentation site's blog, feed and llms.txt agree.

The build writes one page per published post under `blog/`, an RSS 2.0 feed at
`blog/feed.xml` and a `## Blog` section in `llms.txt`. All three must name the
same posts. A draft (a post whose frontmatter says `draft: true`) must leave no
trace: no built page, no sitemap entry, no feed item and no `llms.txt` line.

Usage: python3 tools/check_docs_blog.py [built-site-dir [blog-source-dir]]
With no arguments it checks docs/.vitepress/dist against docs/blog (run
`npm run build` in docs/ first).
"""

import pathlib
import re
import sys
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parent.parent
SITE_URL = "https://bundlemcp.dev"
FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
DRAFT = re.compile(r"^draft:\s*true\s*$", re.MULTILINE)
LLMS_LINK = re.compile(r"^- \[[^\]]*\]\(([^)]+)\)", re.MULTILINE)


def post_url(slug: str) -> str:
    return f"{SITE_URL}/blog/{slug}"


def draft_slugs(blog_source: pathlib.Path) -> set[str]:
    """The slugs of the posts marked `draft: true`."""
    slugs = set()
    for path in blog_source.glob("*.md"):
        frontmatter = FRONTMATTER.match(path.read_text())
        if path.name != "index.md" and frontmatter and DRAFT.search(frontmatter.group(1)):
            slugs.add(path.stem)
    return slugs


def built_post_urls(site: pathlib.Path) -> set[str]:
    """The URL of every post page the build rendered."""
    return {
        post_url(path.stem) for path in (site / "blog").glob("*.html") if path.name != "index.html"
    }


def feed_problems(feed_xml: str) -> tuple[list[str], set[str]]:
    """What is wrong with the feed as RSS 2.0, and the post URLs its items link."""
    try:
        rss = ET.fromstring(feed_xml)  # noqa: S314 - the feed this repository's own build wrote
    except ET.ParseError as error:
        return [f"blog/feed.xml is not well-formed XML: {error} (DOC-22)"], set()
    problems = []
    if rss.tag != "rss" or rss.get("version") != "2.0":
        problems.append("blog/feed.xml is not an RSS 2.0 document (DOC-22)")
    channel = rss.find("channel")
    if channel is None:
        return [*problems, "blog/feed.xml has no channel (DOC-22)"], set()
    problems += [
        f"blog/feed.xml: the channel has no {name} (DOC-22)"
        for name in ("title", "link", "description")
        if not (channel.findtext(name) or "").strip()
    ]
    links = set()
    for item in channel.findall("item"):
        link = (item.findtext("link") or "").strip()
        if not link or not (item.findtext("title") or "").strip():
            problems.append("blog/feed.xml: an item has no title or link (DOC-22)")
        links.add(link)
    return problems, links


def llms_blog_urls(llms_txt: str) -> set[str]:
    """The links listed under `## Blog` in llms.txt."""
    section = re.search(r"^## Blog\n(.*?)(?=^## |\Z)", llms_txt, re.MULTILINE | re.DOTALL)
    return set(LLMS_LINK.findall(section.group(1))) if section else set()


def blog_problems(site: pathlib.Path, blog_source: pathlib.Path) -> list[str]:
    """Everything the built blog gets wrong; empty when pages, feed and llms.txt agree."""
    feed = site / "blog/feed.xml"
    if not feed.is_file():
        return ["blog/feed.xml was not built (DOC-22)"]
    problems, feed_urls = feed_problems(feed.read_text())
    posts = built_post_urls(site)
    llms = llms_blog_urls((site / "llms.txt").read_text())
    for name, listed in (("blog/feed.xml", feed_urls), ("llms.txt", llms)):
        problems += [
            f"{url}: built post missing from {name} (DOC-22)" for url in sorted(posts - listed)
        ]
        problems += [
            f"{url}: in {name} but no such post was built (DOC-22)"
            for url in sorted(listed - posts)
        ]
    sitemap = (site / "sitemap.xml").read_text()
    for slug in sorted(draft_slugs(blog_source)):
        url = post_url(slug)
        traces = [
            name
            for name, present in (
                ("a built page", (site / f"blog/{slug}.html").exists()),
                ("sitemap.xml", f"<loc>{url}</loc>" in sitemap),
                ("blog/feed.xml", url in feed_urls),
                ("llms.txt", url in (site / "llms.txt").read_text()),
            )
            if present
        ]
        if traces:
            problems.append(f"draft blog/{slug}.md is published: {', '.join(traces)} (DOC-22)")
    return problems


def main(argv: list[str]) -> int:
    site = pathlib.Path(argv[0]) if argv else ROOT / "docs/.vitepress/dist"
    blog_source = pathlib.Path(argv[1]) if len(argv) > 1 else ROOT / "docs/blog"
    problems = blog_problems(site, blog_source)
    if problems:
        sys.stderr.write("\n".join(problems) + "\n")
        return 1
    count = len(built_post_urls(site))
    sys.stderr.write(
        f"The feed and llms.txt list all {count} published posts; no draft was built.\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
