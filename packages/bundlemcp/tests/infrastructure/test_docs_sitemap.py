"""The docs site's sitemap check: built pages, sitemap entries and robots.txt (DOC-13)."""

import importlib.util
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[4]
_spec = importlib.util.spec_from_file_location(
    "check_docs_sitemap", ROOT / "tools/check_docs_sitemap.py"
)
assert _spec is not None and _spec.loader is not None
sitemap = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sitemap)

ROBOTS = "User-agent: *\nAllow: /\n\nSitemap: https://bundlemcp.com/sitemap.xml\n"


def _site(tmp_path: pathlib.Path, pages: list[str], locs: list[str], robots: str = ROBOTS):
    for page in pages:
        path = tmp_path / page
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("<html></html>")
    entries = "".join(f"<url><loc>{loc}</loc></url>" for loc in locs)
    (tmp_path / "sitemap.xml").write_text(f'<?xml version="1.0"?><urlset>{entries}</urlset>')
    (tmp_path / "robots.txt").write_text(robots)
    return tmp_path


@pytest.mark.parametrize(
    ("built", "url"),
    [
        ("index.html", "https://bundlemcp.com/"),
        ("guide/index.html", "https://bundlemcp.com/guide/"),
        ("guide/quickstart.html", "https://bundlemcp.com/guide/quickstart"),
    ],
)
def test_doc13_a_built_page_has_its_clean_url(built, url):
    assert sitemap.page_url(pathlib.PurePosixPath(built)) == url


def test_doc13_a_matching_sitemap_passes(tmp_path):
    site = _site(
        tmp_path,
        ["index.html", "guide/quickstart.html", "404.html"],
        ["https://bundlemcp.com/", "https://bundlemcp.com/guide/quickstart"],
    )
    assert sitemap.main([str(site)]) == 0


def test_doc13_the_not_found_page_needs_no_entry(tmp_path):
    site = _site(tmp_path, ["index.html", "404.html"], ["https://bundlemcp.com/"])
    assert sitemap.built_page_urls(site) == {"https://bundlemcp.com/"}


def test_doc13_a_page_missing_from_the_sitemap_fails():
    problems = sitemap.sitemap_problems(
        {"https://bundlemcp.com/", "https://bundlemcp.com/guide/quickstart"},
        {"https://bundlemcp.com/"},
        ROBOTS,
    )
    assert problems == [
        "https://bundlemcp.com/guide/quickstart: built page missing from sitemap.xml (DOC-13)"
    ]


def test_doc13_an_entry_without_a_page_fails():
    problems = sitemap.sitemap_problems(
        {"https://bundlemcp.com/"},
        {"https://bundlemcp.com/", "https://example.com/guide/gone"},
        ROBOTS,
    )
    assert problems == [
        "https://example.com/guide/gone: listed in sitemap.xml but no such page was built (DOC-13)"
    ]


def test_doc13_robots_without_the_sitemap_fails():
    problems = sitemap.sitemap_problems(set(), set(), "User-agent: *\nAllow: /\n")
    assert problems == ["robots.txt does not name https://bundlemcp.com/sitemap.xml (DOC-13)"]


def test_doc13_an_unbuilt_site_fails(tmp_path):
    assert sitemap.main([str(tmp_path)]) == 1
