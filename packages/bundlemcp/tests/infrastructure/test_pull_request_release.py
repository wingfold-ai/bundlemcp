"""The release each pull request carries: labels, version and changelog entry (DEP-12)."""

import importlib.util
import pathlib
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[4]
_spec = importlib.util.spec_from_file_location(
    "pull_request_release", ROOT / "tools/pull_request_release.py"
)
assert _spec is not None and _spec.loader is not None
release = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(release)

URL = "https://github.com/wingfold-ai/bundlemcp/pull/140"

BASE_CHANGELOG = """# Changelog

Intro.

## [1.1.0] - 2026-10-01

### Added

- Something earlier.

## Before 0.1.0

History.
"""


@pytest.mark.parametrize(
    ("title", "labels"),
    [
        ("feat(bundles): Order members by hand", ["type: feat", "semver: minor"]),
        ("fix(auth): Reject expired tokens", ["type: fix", "semver: patch"]),
        ("perf(gateway): Cache the tool list", ["type: perf", "semver: patch"]),
        ("refactor(auth)!: Rename the session cookie", ["type: refactor", "semver: major"]),
        ("docs(repo): Describe the release flow", ["type: docs", "semver: none"]),
        ("chore: Bump a pin", ["type: chore", "semver: none"]),
    ],
)
def test_dep12_title_derives_type_and_semver_labels(title, labels):
    assert release.parse_title(title).labels == labels


@pytest.mark.parametrize(
    "title",
    ["Update stuff", "feature(bundles): Order members", "feat(bundles):Order", "feat(Bundles): X"],
)
def test_dep12_title_that_is_no_conventional_commit_fails(title):
    with pytest.raises(release.ReleaseError, match="expected <type>"):
        release.parse_title(title)


def test_dep12_title_over_72_characters_fails():
    with pytest.raises(release.ReleaseError, match="within 72"):
        release.parse_title("feat(bundles): " + "x" * 60)


@pytest.mark.parametrize(
    ("current", "bump", "expected"),
    [
        ("0.1.0", "major", "0.2.0"),
        ("0.1.0", "minor", "0.1.1"),
        ("0.1.0", "patch", "0.1.1"),
        ("1.1.0", "major", "2.0.0"),
        ("1.1.0", "minor", "1.2.0"),
        ("1.1.0", "patch", "1.1.1"),
        ("1.1.3", "none", "1.1.3"),
    ],
)
def test_dep12_next_version_moves_one_place_right_below_1_0(current, bump, expected):
    assert release.next_version(current, bump) == expected


def _run(*args: str, cwd: pathlib.Path) -> str:
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True).stdout


def _write(tree: pathlib.Path, version: str, changelog: str) -> None:
    files = {
        "CHANGELOG.md": changelog,
        "pyproject.toml": f'[project]\nname = "bundlemcp-workspace"\nversion = "{version}"\n',
        release.PACKAGE_PYPROJECT: f'[project]\nname = "bundlemcp"\nversion = "{version}"\n',
        "uv.lock": (
            f'[[package]]\nname = "bundlemcp"\nversion = "{version}"\n\n'
            f'[[package]]\nname = "bundlemcp-workspace"\nversion = "{version}"\n\n'
            '[[package]]\nname = "httpx"\nversion = "0.28.1"\n'
        ),
        "apps/web/openapi.json": (
            '{\n  "info": {\n    "title": "bundlemcp",\n'
            f'    "version": "{version}"\n  }},\n  "x": {{"version": "9"}}\n}}\n'
        ),
        release.HOOK_SOURCE: "METERING_PROTOCOL_VERSION = 2\n",
    }
    for path, content in files.items():
        (tree / path).parent.mkdir(parents=True, exist_ok=True)
        (tree / path).write_text(content)


@pytest.fixture
def tree(tmp_path: pathlib.Path) -> pathlib.Path:
    """A repository whose ``main`` is at 1.1.0, with a feature branch checked out."""
    _run("git", "init", "-q", "-b", "main", cwd=tmp_path)
    _run("git", "config", "user.email", "t@example.com", cwd=tmp_path)
    _run("git", "config", "user.name", "t", cwd=tmp_path)
    _write(tmp_path, "1.1.0", BASE_CHANGELOG)
    _run("git", "add", "-A", cwd=tmp_path)
    _run("git", "commit", "-qm", "base", cwd=tmp_path)
    _run("git", "switch", "-qc", "feature", cwd=tmp_path)
    return tmp_path


def _apply(tree, title, text=None, date="2026-10-20"):
    return release.apply(
        tree, "main", release.parse_title(title), number=140, url=URL, date=date, text=text
    )


TEXT = "### Added\n\n- Order a bundle's members by hand ([#140](" + URL + "))"


def test_dep12_feature_gets_a_minor_entry_above_the_newest_and_a_bump(tree):
    assert _apply(tree, "feat(bundles): Order members by hand", TEXT) == "1.2.0"
    changelog = (tree / "CHANGELOG.md").read_text()
    assert changelog.index("## [1.2.0] - 2026-10-20") < changelog.index("## [1.1.0]")
    assert "## [1.2.0] - 2026-10-20\n\n" + TEXT in changelog
    assert "Metering-hook protocol" not in changelog
    assert 'version = "1.2.0"' in (tree / "pyproject.toml").read_text()
    lock = (tree / "uv.lock").read_text()
    assert lock.count('version = "1.2.0"') == 2 and 'version = "0.28.1"' in lock
    openapi = (tree / "apps/web/openapi.json").read_text()
    assert '"version": "1.2.0"' in openapi and '"version": "9"' in openapi


def test_dep12_entry_passes_the_release_notes_check(tree):
    _apply(tree, "feat(bundles): Order members by hand", TEXT)
    notes_spec = importlib.util.spec_from_file_location("rn", ROOT / "tools/release_notes.py")
    assert notes_spec is not None and notes_spec.loader is not None
    notes = importlib.util.module_from_spec(notes_spec)
    notes_spec.loader.exec_module(notes)
    notes.check((tree / "CHANGELOG.md").read_text())
    assert "Order a bundle's members" in notes.notes(
        "1.2.0", (tree / "CHANGELOG.md").read_text(), 2, previous_tag=None, previous=None
    )


def test_dep12_rerun_is_idempotent(tree):
    _apply(tree, "feat(bundles): Order members by hand", TEXT)
    first = (tree / "CHANGELOG.md").read_text()
    _apply(tree, "feat(bundles): Order members by hand")
    assert (tree / "CHANGELOG.md").read_text() == first


def test_dep12_retitle_renumbers_and_keeps_the_text(tree):
    _apply(tree, "fix(bundles): Order members by hand", TEXT)
    assert "## [1.1.1]" in (tree / "CHANGELOG.md").read_text()
    assert _apply(tree, "feat(bundles): Order members by hand", date="2026-10-21") == "1.2.0"
    changelog = (tree / "CHANGELOG.md").read_text()
    assert "## [1.1.1]" not in changelog
    assert "## [1.2.0] - 2026-10-21" in changelog and TEXT in changelog


def test_dep12_main_moving_on_renumbers_above_the_merged_entry(tree):
    _apply(tree, "feat(bundles): Order members by hand", TEXT)
    _run("git", "add", "-A", cwd=tree)
    _run("git", "commit", "-qm", "entry", cwd=tree)
    _run("git", "switch", "-q", "main", cwd=tree)
    merged = BASE_CHANGELOG.replace(
        "## [1.1.0]",
        "## [1.2.0] - 2026-10-19\n\nMetering-hook protocol: 2\n\n- Other.\n\n## [1.1.0]",
    )
    _write(tree, "1.2.0", merged)
    _run("git", "commit", "-qam", "other release", cwd=tree)
    _run("git", "switch", "-q", "feature", cwd=tree)
    assert _apply(tree, "feat(bundles): Order members by hand") == "1.3.0"
    assert _run("git", "log", "-1", "--format=%P", cwd=tree).count(" ") == 1
    assert "[skip ci]" in _run("git", "log", "-1", "--format=%s", cwd=tree)
    changelog = (tree / "CHANGELOG.md").read_text()
    assert changelog.index("## [1.3.0]") < changelog.index("## [1.2.0] - 2026-10-19")
    assert TEXT in changelog and "- Other." in changelog


def test_dep12_semver_none_removes_an_earlier_entry_and_bump(tree):
    _apply(tree, "feat(bundles): Order members by hand", TEXT)
    assert _apply(tree, "docs(bundles): Order members by hand") is None
    assert (tree / "CHANGELOG.md").read_text() == BASE_CHANGELOG
    assert 'version = "1.1.0"' in (tree / "pyproject.toml").read_text()


def test_dep12_missing_text_falls_back_to_the_subject(tree):
    _apply(tree, "refactor(auth)!: Rename the session cookie")
    changelog = (tree / "CHANGELOG.md").read_text()
    assert "## [2.0.0]" in changelog
    assert f"### Changed\n\n- **Breaking:** Rename the session cookie ([#140]({URL}))" in changelog


def test_dep12_text_status_tells_an_edited_entry_from_a_generated_one(tree):
    assert release.text_status(tree, "main", None) == "missing"
    _apply(tree, "feat(bundles): Order members by hand", TEXT)
    _run("git", "commit", "-qam", "bot entry", cwd=tree)
    bot = _run("git", "rev-parse", "HEAD", cwd=tree).strip()
    assert release.text_status(tree, "main", bot) == "generated"
    _apply(tree, "feat(bundles): Order members by hand", date="2026-10-22")
    assert release.text_status(tree, "main", bot) == "generated"
    changelog = (tree / "CHANGELOG.md").read_text()
    (tree / "CHANGELOG.md").write_text(changelog.replace("by hand", "in any order"))
    assert release.text_status(tree, "main", bot) == "edited"
    _apply(tree, "fix(bundles): Order members by hand")
    assert "in any order" in (tree / "CHANGELOG.md").read_text()


def test_dep12_conflict_outside_the_owned_files_is_left_to_the_author(tree):
    (tree / "code.py").write_text("branch\n")
    _run("git", "add", "-A", cwd=tree)
    _run("git", "commit", "-qm", "branch code", cwd=tree)
    _run("git", "switch", "-q", "main", cwd=tree)
    (tree / "code.py").write_text("main\n")
    _run("git", "add", "-A", cwd=tree)
    _run("git", "commit", "-qm", "main code", cwd=tree)
    _run("git", "switch", "-q", "feature", cwd=tree)
    with pytest.raises(release.ReleaseError, match="conflicts in code.py"):
        _apply(tree, "feat(bundles): Order members by hand", TEXT)
    assert _run("git", "status", "--porcelain", cwd=tree) == ""


def test_dep12_the_branch_s_own_changelog_edits_outside_the_entry_are_kept(tree):
    edited = BASE_CHANGELOG.replace("Intro.", "A better intro.")
    (tree / "CHANGELOG.md").write_text(edited)
    _apply(tree, "feat(bundles): Order members by hand", TEXT)
    changelog = (tree / "CHANGELOG.md").read_text()
    assert "A better intro." in changelog
    assert changelog.index("A better intro.") < changelog.index("## [1.2.0]")
    _apply(tree, "docs(bundles): Order members by hand")
    assert (tree / "CHANGELOG.md").read_text() == edited


def _change_protocol(tree, version):
    (tree / release.HOOK_SOURCE).write_text(f"METERING_PROTOCOL_VERSION = {version}\n")


def test_dep12_an_unchanged_protocol_is_not_named(tree):
    _apply(tree, "feat(bundles): Order members by hand", TEXT)
    assert "metering-hook protocol" not in (tree / "CHANGELOG.md").read_text().lower()


def test_dep12_a_protocol_change_adds_a_breaking_bullet(tree):
    _change_protocol(tree, 3)
    _apply(tree, "feat(metering)!: Tell the hook more", TEXT)
    changelog = (tree / "CHANGELOG.md").read_text()
    entry = changelog[changelog.index("## [2.0.0]") : changelog.index("## [1.1.0]")]
    assert "### Changed\n\n- **Breaking:** The metering-hook protocol is now 3 (was 2)" in entry
    assert entry.index("### Added") < entry.index("### Changed")


def test_dep12_a_protocol_change_the_text_names_is_not_named_twice(tree):
    _change_protocol(tree, 3)
    text = "### Changed\n\n- **Breaking:** Metering-hook protocol 3 sends `scratch`."
    _apply(tree, "feat(metering)!: Tell the hook more", text)
    assert (tree / "CHANGELOG.md").read_text().lower().count("metering-hook protocol") == 1


def test_dep12_a_protocol_change_without_a_breaking_title_is_refused(tree):
    _change_protocol(tree, 3)
    with pytest.raises(release.ReleaseError, match="mark the title with '!'"):
        _apply(tree, "feat(metering): Tell the hook more", TEXT)
