#!/usr/bin/env python3
"""Resolve every relative Markdown link and heading anchor across the repository.

The VitePress build already fails on a dead link, but only for the pages it
builds: ``docs/.vitepress/config.ts`` excludes ``arc42/**``, ``adr/**``,
``likec4/**`` and every ``README.md``. Those, plus ``CLAUDE.md``, ``openspec/`` and
``.claude/docs/``, are checked here instead — and anchors are checked
everywhere, which the VitePress build does not do at all.

Handles the three link shapes this repository uses:

* ordinary relative paths, with or without an anchor;
* VitePress site-absolute paths (``/guide/concepts``), which resolve under
  ``docs/`` and carry no ``.md`` extension because ``cleanUrls`` is on;
* bare directory links (``docs/likec4/``).

External links, ``mailto:`` and pure in-page anchors to generated content are
skipped. Anchors are matched against GitHub/VitePress heading slugs.
"""

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

IGNORED = {"node_modules", ".vitepress", "dist", ".venv"}


def _tracked(paths: list[pathlib.Path]) -> list[pathlib.Path]:
    """Markdown this repository owns, not what a package manager installed."""
    return sorted(p for p in paths if IGNORED.isdisjoint(p.parts))


TARGETS = _tracked(
    [
        *DOCS.rglob("*.md"),
        *ROOT.glob("*.md"),
        *(ROOT / ".claude" / "docs").glob("*.md"),
        *(ROOT / "openspec").rglob("*.md"),
        *(ROOT / "packages").rglob("README.md"),
        *(ROOT / "deploy").glob("*.md"),
    ]
)

LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
HEADING = re.compile(r"^#{1,6}\s+(.*?)\s*$", re.MULTILINE)
CUSTOM_ANCHOR = re.compile(r"\{#([\w-]+)\}\s*$")
SKIP_PREFIXES = ("http://", "https://", "mailto:", "#/", "data:")


def slugs(heading: str) -> set[str]:
    """Both anchors a heading can have, because the two renderers disagree.

    GitHub replaces each space with its own hyphen, so removing a symbol such as
    an arrow leaves a double hyphen. VitePress collapses runs of whitespace into
    one. Files under docs/arc42 and the READMEs are read on GitHub, site pages are
    rendered by VitePress, so both spellings are accepted rather than guessing
    which renderer a given file is read in.
    """
    custom = CUSTOM_ANCHOR.search(heading)
    if custom:  # VitePress `{#id}`: that id replaces the generated slug
        return {custom.group(1)}
    text = re.sub(r"`([^`]*)`", r"\1", heading)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"[*_]", "", text)
    text = re.sub(r"[^\w\s-]", "", text.lower()).strip()
    return {re.sub(r"\s", "-", text), re.sub(r"\s+", "-", text)}


def anchors(path: pathlib.Path) -> set[str]:
    return {a for h in HEADING.findall(path.read_text()) for a in slugs(h)}


def resolve(source: pathlib.Path, target: str) -> pathlib.Path | None:
    """The file a link points at, or None when it resolves to nothing."""
    if target.startswith("/"):
        # A VitePress site-absolute link; cleanUrls means the .md is implied, and
        # files under docs/public/ are served from the site root.
        candidates = [DOCS / target.lstrip("/"), DOCS / "public" / target.lstrip("/")]
    else:
        candidates = [source.parent / target]
    for base in candidates:
        for candidate in (base, base.with_suffix(".md"), base / "index.md"):
            if candidate.is_file():
                return candidate
        if base.is_dir():
            return base
    return None


def main() -> int:
    problems: list[str] = []
    for source in TARGETS:
        rel = source.relative_to(ROOT)
        for number, line in enumerate(source.read_text().splitlines(), start=1):
            for raw in LINK.findall(line):
                if raw.startswith(SKIP_PREFIXES):
                    continue
                target, _, anchor = raw.partition("#")
                if not target:
                    if anchor and anchor not in anchors(source):
                        problems.append(f"{rel}:{number}: no heading for anchor #{anchor}")
                    continue
                resolved = resolve(source, target)
                if resolved is None:
                    problems.append(f"{rel}:{number}: {target} does not exist")
                elif anchor and resolved.is_file() and anchor not in anchors(resolved):
                    problems.append(f"{rel}:{number}: {target} has no heading for anchor #{anchor}")

    if problems:
        sys.stderr.write("\n".join(f"  {p}" for p in problems))
        sys.stderr.write(f"\n\n{len(problems)} broken link(s) or anchor(s).\n")
        return 1
    sys.stderr.write(f"All relative links and anchors resolve across {len(TARGETS)} files.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
