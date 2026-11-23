"""Release notes from the changelog, naming the metering-hook protocol version (DEP-11)."""

import importlib.util
import pathlib
import subprocess

import pytest
from bundlemcp.application.metering.metering_hook import METERING_PROTOCOL_VERSION

ROOT = pathlib.Path(__file__).resolve().parents[4]
_spec = importlib.util.spec_from_file_location("release_notes", ROOT / "tools/release_notes.py")
assert _spec is not None and _spec.loader is not None
release_notes = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(release_notes)

CHANGELOG = """# Changelog

## [1.2.0] - 2026-11-01

### Changed

- **Breaking:** The metering-hook protocol is now 3 (was 2); hooks must be updated.
- The hook is told more.

## [1.1.0] - 2026-10-01

### Fixed

- Something.
"""


def test_dep11_the_repository_changelog_is_well_formed():
    """DEP-11: every entry of the repository's changelog has a dated heading, newest first."""
    release_notes.check((ROOT / "CHANGELOG.md").read_text())
    source = (ROOT / release_notes.HOOK_SOURCE).read_text()
    assert release_notes.source_protocol(source) == METERING_PROTOCOL_VERSION


def test_dep11_notes_carry_the_entry_and_call_out_a_protocol_change():
    """DEP-11: the notes are the version's entry, and say the protocol changed since the
    previous release."""
    text = release_notes.notes("1.2.0", CHANGELOG, 3, previous_tag="v1.1.0", previous=2)
    assert "The hook is told more." in text
    assert "2026-11-01" not in text  # the heading's date is not part of the notes
    assert "**3**, **changed** from 2 in v1.1.0" in text


def test_dep11_an_unchanged_protocol_is_stated_as_unchanged():
    text = release_notes.notes("1.1.0", CHANGELOG, 2, previous_tag="v1.0.5", previous=2)
    assert "**2**, unchanged since v1.0.5" in text


def test_dep11_a_tag_without_a_changelog_entry_is_refused():
    """DEP-11: a release for a version the changelog does not list fails before anything ships."""
    with pytest.raises(release_notes.ReleaseError, match="no entry for 9.9.9"):
        release_notes.notes("9.9.9", CHANGELOG, 3, previous_tag=None, previous=None)


def test_dep12_a_protocol_change_the_entry_does_not_name_is_refused():
    """DEP-12: an entry names the metering-hook protocol in the release that changes it."""
    with pytest.raises(release_notes.ReleaseError, match="does not say so"):
        release_notes.notes("1.1.0", CHANGELOG, 3, previous_tag="v1.0.0", previous=2)


@pytest.mark.parametrize(
    "changelog",
    [
        "# Changelog\n\n## [Unreleased]\n\n- something\n",
        "# Changelog\n\n## [1.2.0]\n\n- something\n",
        "# Changelog\n\n## [1.1.0] - 2026-10-01\n\n## [1.2.0] - 2026-11-01\n",
        "# Changelog\n\n## [1.2.0] - 2026-11-01\n\n## [1.2.0] - 2026-10-01\n",
        "# Changelog\n",
    ],
)
def test_dep11_a_malformed_changelog_fails_the_check(changelog):
    with pytest.raises(release_notes.ReleaseError):
        release_notes.check(changelog)


def test_dep11_a_history_section_below_the_versions_is_not_part_of_the_last_entry():
    """DEP-11: the pre-release history below the versions stays out of the oldest notes."""
    changelog = CHANGELOG + "\n## Before 1.1.0\n\n### feat: something (#1)\n\nHistory.\n"
    text = release_notes.notes("1.1.0", changelog, 2, previous_tag=None, previous=None)
    assert "History." not in text and "Before 1.1.0" not in text
    assert set(release_notes.entries(changelog)) == {"1.2.0", "1.1.0"}


def test_dep11_notes_frame_the_entry():
    """DEP-11: the notes open with what bundlemcp is, then the entry, the images to run, where to
    start and give feedback, the comparison with the previous tag, and end with the protocol."""
    text = release_notes.notes(
        "1.2.0", CHANGELOG, 3, previous_tag="v1.1.0", previous=2, repo="acme/bundlemcp"
    )
    assert text.startswith(release_notes.PROJECT)
    order = [
        "The hook is told more.",
        "ghcr.io/acme/bundlemcp-gateway:1.2.0",
        "ghcr.io/acme/bundlemcp-web:1.2.0",
        "https://bundlemcp.dev/guide/quickstart",
        "https://github.com/acme/bundlemcp/discussions",
        "**Full Changelog**: https://github.com/acme/bundlemcp/compare/v1.1.0...v1.2.0",
        "Metering-hook protocol version",
    ]
    positions = [text.index(part) for part in order]
    assert positions == sorted(positions)
    assert text.rstrip().splitlines()[-1].startswith("Metering-hook protocol version")


def test_dep11_preview_caveat_only_below_1_0():
    """DEP-11: a release below 1.0 says a minor release may still break; 1.0 and later do not."""
    changelog = (
        "# Changelog\n\n## [1.0.0] - 2026-12-01\n\n- Stable.\n\n"
        "## [0.5.0] - 2026-11-01\n\n- Preview.\n"
    )
    preview = release_notes.notes("0.5.0", changelog, 2, previous_tag=None, previous=None)
    stable = release_notes.notes("1.0.0", changelog, 2, previous_tag="v0.5.0", previous=2)
    assert release_notes.PREVIEW in preview
    assert release_notes.PREVIEW not in stable


def test_dep11_first_release_has_no_compare_link():
    """DEP-11: without a previous release tag there is nothing to compare with."""
    text = release_notes.notes("1.1.0", CHANGELOG, 2, previous_tag=None, previous=None)
    assert "Full Changelog" not in text


def _git(*args: str, cwd: pathlib.Path) -> None:
    command = ("git", *args)
    subprocess.run(command, cwd=cwd, check=True, capture_output=True)


def _release(tree: pathlib.Path, version: str, entry: str) -> None:
    changelog = tree / "CHANGELOG.md"
    previous = changelog.read_text() if changelog.exists() else "# Changelog\n"
    head, _, rest = previous.partition("\n")
    changelog.write_text(f"{head}\n\n## [{version}] - 2026-11-01\n\n- {entry}\n{rest}")
    _git("add", "-A", cwd=tree)
    _git("commit", "-qm", f"release {version}", cwd=tree)
    _git("tag", f"v{version}", cwd=tree)


@pytest.fixture
def tagged(tmp_path: pathlib.Path) -> pathlib.Path:
    _git("init", "-q", "-b", "main", cwd=tmp_path)
    _git("config", "user.email", "test@example.invalid", cwd=tmp_path)
    _git("config", "user.name", "Test", cwd=tmp_path)
    hook = tmp_path / release_notes.HOOK_SOURCE
    hook.parent.mkdir(parents=True)
    hook.write_text("METERING_PROTOCOL_VERSION = 2\n")
    _release(tmp_path, "1.1.0", "First.")
    _release(tmp_path, "1.2.0", "Second.")
    return tmp_path


def test_dep11_notes_take_the_current_entry_and_the_protocol_the_tag_shipped(tagged):
    """DEP-11: a corrected changelog reaches an older release's notes, while the protocol line
    states the version that tag shipped."""
    (tagged / release_notes.HOOK_SOURCE).write_text("METERING_PROTOCOL_VERSION = 3\n")
    changelog = (tagged / "CHANGELOG.md").read_text()
    (tagged / "CHANGELOG.md").write_text(changelog.replace("- First.", "- First, corrected."))
    first = release_notes.tag_notes("v1.1.0", root=tagged)
    assert "- First, corrected." in first and "Second." not in first
    assert "Full Changelog" not in first and "**2**" in first
    second = release_notes.tag_notes("v1.2.0", root=tagged)
    assert "- Second." in second and "compare/v1.1.0...v1.2.0" in second


def test_dep11_only_the_highest_version_is_latest(tagged):
    """DEP-11: a patch tagged for an older line does not take over the latest release."""
    _git("tag", "v1.1.1", "v1.1.0", cwd=tagged)
    assert release_notes.is_latest("v1.2.0", root=tagged)
    assert not release_notes.is_latest("v1.1.1", root=tagged)
