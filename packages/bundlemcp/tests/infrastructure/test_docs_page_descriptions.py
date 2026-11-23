"""Discovery of the documentation site: page descriptions and llms.txt (DOC-20, DOC-21)."""

import pathlib
import re

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[4]
DOCS = ROOT / "docs"
CONFIG = DOCS / ".vitepress/config.ts"
EXCLUDED = ("arc42/", "adr/", "likec4/", "brand/", "node_modules/", ".vitepress/")
MAX_LENGTH = 160


def published_pages() -> list[pathlib.Path]:
    pages = []
    for path in sorted(DOCS.rglob("*.md")):
        relative = path.relative_to(DOCS).as_posix()
        if relative.startswith(EXCLUDED) or path.name == "README.md":
            continue
        pages.append(path)
    return pages


def description(path: pathlib.Path) -> str | None:
    text = path.read_text()
    if not text.startswith("---\n"):
        return None
    meta = yaml.safe_load(text[4:].split("\n---\n", 1)[0]) or {}
    return meta.get("description")


@pytest.mark.parametrize("page", published_pages(), ids=lambda p: p.relative_to(DOCS).as_posix())
def test_doc20_every_page_has_its_own_description(page):
    """DOC-20: every published page declares a description short enough for a search result."""
    text = description(page)
    assert text, f"{page.relative_to(DOCS)} has no description (DOC-20)"
    assert len(text) <= MAX_LENGTH, (
        f"{page.relative_to(DOCS)}: description is {len(text)} characters, at most {MAX_LENGTH}"
    )


def test_doc20_no_two_pages_share_a_description():
    """DOC-20: each page describes itself, so no description repeats."""
    texts = [description(page) for page in published_pages()]
    assert len(texts) == len(set(texts))


def test_doc21_llms_txt_follows_the_sidebar():
    """DOC-21: the build writes llms.txt from the sidebar, and every sidebar link names a page
    that exists."""
    config = CONFIG.read_text()
    assert "await writeLlmsFiles(siteConfig, siteUrl)" in config
    links = re.findall(r'link: "(/[a-z0-9/-]+)"', config.split("sidebar: [", 1)[1])
    assert links
    for link in links:
        assert (DOCS / f"{link.lstrip('/')}.md").is_file(), f"sidebar link {link} has no page"
