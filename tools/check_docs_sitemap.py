#!/usr/bin/env python3
"""Check that the built documentation site's sitemap lists exactly its pages.

Search engines learn the site's pages from `sitemap.xml`, which `robots.txt`
names. Every built page must appear there under the site's public address, by
its clean URL, and the sitemap must list nothing the build did not render. The
not-found page is not a page anyone should land on from a search, so it is left
out.

Usage: python3 tools/check_docs_sitemap.py [built-site-dir]
With no argument it checks docs/.vitepress/dist (run `npm run build` in docs/ first).
"""

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SITE_URL = "https://bundlemcp.dev"
SITEMAP_URL = f"{SITE_URL}/sitemap.xml"
NOT_FOUND_PAGE = "404.html"
LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>")


def page_url(relative: pathlib.PurePosixPath) -> str:
    """The clean public URL of a built page, from its path inside the site."""
    if relative.name == "index.html":
        parent = relative.parent.as_posix()
        return f"{SITE_URL}/" if parent == "." else f"{SITE_URL}/{parent}/"
    return f"{SITE_URL}/{relative.with_suffix('').as_posix()}"


def built_page_urls(site: pathlib.Path) -> set[str]:
    """The URL of every page the build rendered, the not-found page excluded."""
    return {
        page_url(pathlib.PurePosixPath(path.relative_to(site).as_posix()))
        for path in site.rglob("*.html")
        if path.relative_to(site).as_posix() != NOT_FOUND_PAGE
    }


def sitemap_urls(sitemap_xml: str) -> set[str]:
    """Every `<loc>` the sitemap lists."""
    return set(LOC.findall(sitemap_xml))


def sitemap_problems(pages: set[str], listed: set[str], robots_txt: str) -> list[str]:
    """What is wrong between the built pages, the sitemap and robots.txt; empty when all agree."""
    problems = [
        f"{url}: built page missing from sitemap.xml (DOC-13)" for url in sorted(pages - listed)
    ]
    problems += [
        f"{url}: listed in sitemap.xml but no such page was built (DOC-13)"
        for url in sorted(listed - pages)
    ]
    robots_lines = {line.strip() for line in robots_txt.splitlines()}
    if f"Sitemap: {SITEMAP_URL}" not in robots_lines:
        problems.append(f"robots.txt does not name {SITEMAP_URL} (DOC-13)")
    return problems


def main(argv: list[str]) -> int:
    site = pathlib.Path(argv[0]) if argv else ROOT / "docs/.vitepress/dist"
    sitemap = site / "sitemap.xml"
    robots = site / "robots.txt"
    missing = [str(path) for path in (sitemap, robots) if not path.is_file()]
    if missing:
        sys.stderr.write(f"not built: {', '.join(missing)} (DOC-13)\n")
        return 1
    pages = built_page_urls(site)
    problems = sitemap_problems(pages, sitemap_urls(sitemap.read_text()), robots.read_text())
    if problems:
        sys.stderr.write("\n".join(problems) + "\n")
        return 1
    sys.stderr.write(f"sitemap.xml lists all {len(pages)} built pages; robots.txt names it.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
