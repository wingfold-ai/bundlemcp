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

## [Unreleased]

Metering-hook protocol: 3

## [1.2.0] - 2026-11-01

Metering-hook protocol: 3

### Changed

- The hook is told more.

## [1.1.0] - 2026-10-01

Metering-hook protocol: 2
"""


def test_dep11_the_changelog_names_the_current_protocol_version():
    """DEP-11: the repository's changelog states METERING_PROTOCOL_VERSION in its newest entry."""
    release_notes.check((ROOT / "CHANGELOG.md").read_text(), METERING_PROTOCOL_VERSION)
    source = (ROOT / release_notes.HOOK_SOURCE).read_text()
    assert release_notes.source_protocol(source) == METERING_PROTOCOL_VERSION


def test_dep11_notes_carry_the_entry_and_call_out_a_protocol_change():
    """DEP-11: the notes are the version's entry, and say the protocol changed since the
    previous release."""
    text = release_notes.notes("1.2.0", CHANGELOG, 3, previous_tag="v1.1.0", previous=2)
    assert "The hook is told more." in text
    assert "2026-11-01" not in text  # the heading's date is not part of the notes
    assert "Metering-hook protocol: 3" not in text  # restated once, at the end
    assert "**3**, **changed** from 2 in v1.1.0" in text


def test_dep11_an_unchanged_protocol_is_stated_as_unchanged():
    text = release_notes.notes("1.2.0", CHANGELOG, 3, previous_tag="v1.1.5", previous=3)
    assert "**3**, unchanged since v1.1.5" in text


def test_dep11_a_tag_without_a_changelog_entry_is_refused():
    """DEP-11: a release for a version the changelog does not list fails before anything ships."""
    with pytest.raises(release_notes.ReleaseError, match="no entry for 9.9.9"):
        release_notes.notes("9.9.9", CHANGELOG, 3, previous_tag=None, previous=None)


def test_dep11_an_entry_naming_another_protocol_than_the_source_is_refused():
    with pytest.raises(release_notes.ReleaseError, match="names metering-hook protocol 2"):
        release_notes.notes("1.1.0", CHANGELOG, 3, previous_tag=None, previous=None)


def test_dep11_an_entry_without_a_protocol_line_fails_the_check():
    with pytest.raises(release_notes.ReleaseError, match="does not say"):
        release_notes.check("# Changelog\n\n## [Unreleased]\n\n- something\n", 2)
