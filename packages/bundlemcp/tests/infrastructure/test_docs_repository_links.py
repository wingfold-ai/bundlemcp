"""The docs site's repository-link check: links only once the repository is public (DOC-14)."""

import importlib.util
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[4]
_spec = importlib.util.spec_from_file_location(
    "check_docs_repository_links", ROOT / "tools/check_docs_repository_links.py"
)
assert _spec is not None and _spec.loader is not None
links = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(links)

REPO = "https://github.com/wingfold-ai/bundlemcp"
NOTICE = '<div data-testid="repository-notice">Not public yet</div>'


def _site(tmp_path: pathlib.Path, pages: dict[str, str], ledger: str = "{}") -> pathlib.Path:
    for name, body in pages.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
    (tmp_path / "requirements.json").write_text(ledger)
    return tmp_path


def _private_site(tmp_path, **extra: str) -> pathlib.Path:
    pages = {name: NOTICE for name in links.NOTICE_PAGES}
    pages["guide/concepts.html"] = "<p>CHANGELOG.md</p>"
    return _site(tmp_path, {**pages, **extra})


def test_doc14_a_private_build_without_links_passes(tmp_path):
    assert links.link_problems(_private_site(tmp_path), public=False) == []


def test_doc14_a_private_build_with_a_repository_link_fails(tmp_path):
    site = _private_site(tmp_path, **{"guide/concepts.html": f'<a href="{REPO}/issues">x</a>'})
    assert links.link_problems(site, public=False) == [
        "guide/concepts.html: 1 link(s) into the private repository (DOC-14)"
    ]


def test_doc14_a_repository_link_in_a_requirement_text_fails(tmp_path):
    site = _private_site(tmp_path)
    (site / "requirements.json").write_text(
        f'{{"html": "<a href=\\"{REPO}/blob/main/x.md\\">x</a>"}}'
    )
    assert links.link_problems(site, public=False) == [
        "requirements.json: 1 link(s) into the private repository (DOC-14)"
    ]


def test_doc14_another_github_repository_is_not_ours():
    assert links.repository_links('<a href="https://github.com/wingfold-ai/bundlemcp-extra">') == 0
    assert links.repository_links(f'<a href="{REPO}">') == 1


def test_doc14_a_private_build_needs_the_notice(tmp_path):
    site = _private_site(tmp_path, **{"guide/quickstart.html": "<h1>Quickstart</h1>"})
    assert links.link_problems(site, public=False) == [
        "guide/quickstart.html: no not-public notice while the repository is private (DOC-14)"
    ]


def test_doc14_a_public_build_links_and_shows_no_notice(tmp_path):
    site = _site(tmp_path, {"index.html": f'<a href="{REPO}">GitHub</a>'})
    assert links.link_problems(site, public=True) == []


def test_doc14_a_public_build_with_the_notice_fails(tmp_path):
    site = _site(tmp_path, {"index.html": f'<a href="{REPO}">GitHub</a>{NOTICE}'})
    assert links.link_problems(site, public=True) == [
        "index.html: shows the not-public notice in a public build (DOC-14)"
    ]


def test_doc14_a_public_build_without_any_link_fails(tmp_path):
    site = _site(tmp_path, {"index.html": "<p>no links</p>"})
    assert links.link_problems(site, public=True) == [
        "no page links to the repository in a public build (DOC-14)"
    ]
