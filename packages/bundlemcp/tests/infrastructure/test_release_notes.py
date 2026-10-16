"""Release notes from the changelog, naming the metering-hook protocol version (DEP-11)."""

import importlib.util
import pathlib

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
