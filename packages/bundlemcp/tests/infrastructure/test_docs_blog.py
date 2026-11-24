"""The documentation site's blog: posts, navigation, feed and drafts (DOC-22)."""

import datetime
import importlib.util
import pathlib
import re

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[4]
BLOG = ROOT / "docs/blog"
CONFIG = ROOT / "docs/.vitepress/config.ts"
BLOG_POSTS = ROOT / "docs/.vitepress/blog-posts.ts"
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_spec = importlib.util.spec_from_file_location("check_docs_blog", ROOT / "tools/check_docs_blog.py")
assert _spec is not None and _spec.loader is not None
check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check)


def frontmatter(path: pathlib.Path) -> dict:
    text = path.read_text()
    assert text.startswith("---\n"), f"{path.name} has no frontmatter"
    return yaml.safe_load(text[4:].split("\n---\n", 1)[0]) or {}


def posts() -> list[pathlib.Path]:
    return sorted(path for path in BLOG.glob("*.md") if path.name != "index.md")


def known_authors() -> set[str]:
    table = BLOG_POSTS.read_text().split("AUTHORS", 1)[1].split("};", 1)[0]
    return set(re.findall(r'"([^"]+)": "https://', table))


def test_doc22_every_published_post_declares_its_fields():
    """DOC-22: a post names its title, description, a YYYY-MM-DD date and a known author."""
    authors = known_authors()
    assert authors
    for path in posts():
        meta = frontmatter(path)
        if meta.get("draft") is True:
            continue
        for key in ("title", "description", "author"):
            assert isinstance(meta.get(key), str) and meta[key].strip(), f"{path.name}: no {key}"
        date = meta.get("date")
        assert isinstance(date, datetime.date) or (isinstance(date, str) and DATE.match(date)), (
            f"{path.name}: date must be YYYY-MM-DD"
        )
        assert meta["author"] in authors, f"{path.name}: unknown author {meta['author']!r}"


def test_doc22_a_draft_is_marked_the_way_the_build_detects_it():
    """DOC-22: the build finds drafts by a literal `draft: true` line, so a post YAML reads as a
    draft must be written that way, and one marked that way must read as a draft."""
    drafts = check.draft_slugs(BLOG)
    for path in posts():
        assert (frontmatter(path).get("draft") is True) == (path.stem in drafts), path.name


def test_doc22_blog_sits_before_roadmap_in_the_nav():
    """DOC-22: the top navigation links the blog directly before the roadmap."""
    nav = CONFIG.read_text().split("nav: [", 1)[1].split("],", 1)[0]
    texts = re.findall(r'text: "([^"]+)"', nav)
    assert texts[-2:] == ["Blog", "Roadmap"]
    assert 'link: "/blog/"' in nav


def test_doc22_every_page_announces_the_feed():
    """DOC-22: the shared head carries the RSS autodiscovery link to the feed."""
    config = CONFIG.read_text()
    assert 'rel: "alternate", type: "application/rss+xml"' in config
    assert "href: `${siteUrl}${FEED_PATH}`" in config
    assert "feedDiscovery," in config.split("head: [", 1)[1]


def test_doc22_drafts_are_left_out_of_production_builds():
    """DOC-22: production builds exclude draft sources, so no page or sitemap entry exists."""
    config = CONFIG.read_text()
    assert 'process.env.NODE_ENV === "production" ? draftSources(docsDir) : []' in config
    assert '"**/README.md", ...drafts]' in config


RSS = """<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
<link>https://bundlemcp.dev/blog/</link><description>d</description>{items}</channel></rss>"""


def _item(slug: str) -> str:
    return f"<item><title>{slug}</title><link>https://bundlemcp.dev/blog/{slug}</link></item>"


def _site(tmp_path: pathlib.Path, built: list[str], feed: list[str], llms: list[str]):
    site, source = tmp_path / "dist", tmp_path / "blog"
    (site / "blog").mkdir(parents=True)
    source.mkdir()
    (site / "blog/index.html").write_text("<html></html>")
    for slug in built:
        (site / f"blog/{slug}.html").write_text("<html></html>")
    (site / "blog/feed.xml").write_text(RSS.format(items="".join(_item(s) for s in feed)))
    lines = "".join(f"- [{s}](https://bundlemcp.dev/blog/{s}): d\n" for s in llms)
    (site / "llms.txt").write_text(f"# bundlemcp\n\n## Guide\n\n## Blog\n\n{lines}\n## Optional\n")
    (site / "sitemap.xml").write_text("<urlset></urlset>")
    return site, source


def test_doc22_a_built_post_in_the_feed_and_llms_txt_passes(tmp_path):
    site, source = _site(tmp_path, ["hello"], ["hello"], ["hello"])
    assert check.main([str(site), str(source)]) == 0


def test_doc22_an_empty_blog_passes(tmp_path):
    site, source = _site(tmp_path, [], [], [])
    assert check.main([str(site), str(source)]) == 0


def test_doc22_a_post_missing_from_the_feed_fails(tmp_path):
    site, source = _site(tmp_path, ["hello"], [], ["hello"])
    assert check.blog_problems(site, source) == [
        "https://bundlemcp.dev/blog/hello: built post missing from blog/feed.xml (DOC-22)"
    ]


def test_doc22_a_built_draft_fails(tmp_path):
    site, source = _site(tmp_path, ["hello"], ["hello"], ["hello"])
    (source / "hello.md").write_text("---\ntitle: Hello\ndraft: true\n---\n\nText.\n")
    (problem,) = check.blog_problems(site, source)
    assert problem.startswith("draft blog/hello.md is published: a built page, blog/feed.xml")


def test_doc22_a_feed_that_is_not_rss_2_fails(tmp_path):
    site, source = _site(tmp_path, [], [], [])
    (site / "blog/feed.xml").write_text('<feed xmlns="http://www.w3.org/2005/Atom"></feed>')
    assert "blog/feed.xml is not an RSS 2.0 document (DOC-22)" in check.blog_problems(site, source)
