#!/usr/bin/env python3
"""Check that the built documentation site links into the repository only when it is public.

Until the source repository is public, every link into it reaches GitHub's 404,
so a site built without `DOCS_REPOSITORY_PUBLIC=true` must carry none: no GitHub
icon, no "Edit this page" link, no link in a page or a requirement's text. It
shows a notice instead on the pages whose commands need the repository. Built
with the repository public, the links are back and no notice is shown.

Usage: python3 tools/check_docs_repository_links.py [built-site-dir]
With no argument it checks docs/.vitepress/dist, built with the same
DOCS_REPOSITORY_PUBLIC value as this check runs with.
"""

import os
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
REPOSITORY_URL = "https://github.com/wingfold-ai/bundlemcp"
REPOSITORY_HREF = re.compile(rf'href="{re.escape(REPOSITORY_URL)}(?:/[^"]*)?"')
NOTICE = 'data-testid="repository-notice"'
NOTICE_PAGES = ("index.html", "guide/quickstart.html", "self-hosting/deploy.html")
LEDGER_FILE = "requirements.json"


def repository_links(text: str) -> int:
    """How many links into the repository a built file carries."""
    return len(REPOSITORY_HREF.findall(text.replace('\\"', '"')))


def link_problems(site: pathlib.Path, *, public: bool) -> list[str]:
    """What the built site gets wrong for the repository's visibility; empty when nothing."""
    problems: list[str] = []
    pages = {path.relative_to(site).as_posix(): path.read_text() for path in site.rglob("*.html")}
    if public:
        for name in NOTICE_PAGES:
            if NOTICE in pages.get(name, ""):
                problems.append(f"{name}: shows the not-public notice in a public build (DOC-14)")
        if not any(repository_links(text) for text in pages.values()):
            problems.append("no page links to the repository in a public build (DOC-14)")
        return problems
    ledger = site / LEDGER_FILE
    files = {**pages, LEDGER_FILE: ledger.read_text() if ledger.is_file() else ""}
    for name, text in sorted(files.items()):
        if count := repository_links(text):
            problems.append(f"{name}: {count} link(s) into the private repository (DOC-14)")
    for name in NOTICE_PAGES:
        if NOTICE not in pages.get(name, ""):
            problems.append(
                f"{name}: no not-public notice while the repository is private (DOC-14)"
            )
    return problems


def main(argv: list[str]) -> int:
    site = pathlib.Path(argv[0]) if argv else ROOT / "docs/.vitepress/dist"
    public = os.environ.get("DOCS_REPOSITORY_PUBLIC") == "true"
    if not site.is_dir():
        sys.stderr.write(f"not built: {site} (DOC-14)\n")
        return 1
    problems = link_problems(site, public=public)
    if problems:
        sys.stderr.write("\n".join(problems) + "\n")
        return 1
    mode = "public: repository links shown" if public else "private: no repository links"
    sys.stderr.write(f"The built site matches the repository's visibility ({mode}).\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
