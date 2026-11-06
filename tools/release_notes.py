#!/usr/bin/env python3
"""Release notes from CHANGELOG.md, stating the metering-hook protocol version.

    python3 tools/release_notes.py v1.2.0      # the notes for that tag, on stdout
    python3 tools/release_notes.py --check     # every entry heading is well-formed

Fails (exit 1) when the changelog has no entry for the version, or when the
metering-hook protocol changed since the previous release tag and the entry
does not say so. An entry names the protocol only in a release that changes
it; the notes always end with the version the source ships and whether it
changed since the previous release tag.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHANGELOG = ROOT / "CHANGELOG.md"
HOOK_SOURCE = "packages/bundlemcp/bundlemcp/application/metering/metering_hook.py"
TAG = re.compile(r"^v(\d+\.\d+\.\d+)$")
HEADING = re.compile(r"^## \[([^\]]+)\][^\n]*$", re.MULTILINE)
DATED_HEADING = re.compile(r"^## \[(\d+)\.(\d+)\.(\d+)\] - \d{4}-\d{2}-\d{2}$")
SECTION = re.compile(r"^## ", re.MULTILINE)
NAMES_PROTOCOL = re.compile(r"metering-hook protocol", re.IGNORECASE)
SOURCE_VERSION = re.compile(r"^METERING_PROTOCOL_VERSION = (\d+)", re.MULTILINE)
VERSIONING = "https://bundlemcp.dev/integrate/metering-hook#versioning"


class ReleaseError(Exception):
    """The changelog cannot produce notes for this release."""


def entries(changelog: str) -> dict[str, str]:
    """Each entry's body by its heading, ``Unreleased`` or a version, newest first.

    An entry ends at the next second-level heading of any kind, so a section
    such as the pre-release history below the versions is part of no entry.
    """
    found: dict[str, str] = {}
    sections = list(SECTION.finditer(changelog))
    for section, following in zip(sections, [*sections[1:], None], strict=True):
        heading = HEADING.match(changelog, section.start())
        if heading is None:
            continue
        end = following.start() if following else len(changelog)
        found[heading.group(1)] = changelog[heading.end() : end].strip()
    return found


def source_protocol(source: str) -> int:
    match = SOURCE_VERSION.search(source)
    if match is None:
        raise ReleaseError(f"no METERING_PROTOCOL_VERSION in {HOOK_SOURCE}")
    return int(match.group(1))


def notes(
    version: str,
    changelog: str,
    current: int,
    *,
    previous_tag: str | None,
    previous: int | None,
) -> str:
    """The release notes for ``version``: its changelog entry, then the protocol line."""
    entry = entries(changelog).get(version)
    if entry is None:
        raise ReleaseError(
            f"CHANGELOG.md has no entry for {version}; add '## [{version}] - <date>'"
        )
    changed = previous_tag is not None and previous is not None and previous != current
    if changed and NAMES_PROTOCOL.search(entry) is None:
        raise ReleaseError(
            f"the metering-hook protocol changed from {previous} in {previous_tag} to {current}, "
            f"and the changelog entry {version} does not say so"
        )
    if previous_tag is None or previous is None:
        protocol = f"Metering-hook protocol version: **{current}**."
    elif not changed:
        protocol = f"Metering-hook protocol version: **{current}**, unchanged since {previous_tag}."
    else:
        protocol = (
            f"Metering-hook protocol version: **{current}**, **changed** from {previous} in "
            f"{previous_tag}. Hooks must be updated; see {VERSIONING}."
        )
    return f"{entry}\n\n---\n\n{protocol}\n"


def check(changelog: str) -> None:
    """Every entry is headed ``## [x.y.z] - YYYY-MM-DD``, each version once, newest first."""
    versions: list[tuple[int, int, int]] = []
    for heading in HEADING.finditer(changelog):
        match = DATED_HEADING.match(heading.group(0))
        if match is None:
            raise ReleaseError(f"'{heading.group(0)}' is not '## [x.y.z] - YYYY-MM-DD'")
        versions.append((int(match.group(1)), int(match.group(2)), int(match.group(3))))
    if not versions:
        raise ReleaseError("CHANGELOG.md has no entries")
    if versions != sorted(set(versions), reverse=True):
        raise ReleaseError("CHANGELOG.md lists a version twice or out of order; newest first")


def _git(*args: str) -> str | None:
    done = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    return done.stdout.strip() if done.returncode == 0 else None


def previous_release(tag: str) -> tuple[str | None, int | None]:
    """The release tag before ``tag`` and the protocol version it shipped, if there is one."""
    previous = _git("describe", "--tags", "--abbrev=0", "--match", "v*.*.*", f"{tag}^")
    if previous is None:
        return None, None
    source = _git("show", f"{previous}:{HOOK_SOURCE}")
    return previous, source_protocol(source) if source is not None else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("tag", nargs="?", help="Release tag, e.g. v1.2.0")
    parser.add_argument("--check", action="store_true", help="Validate the changelog only")
    args = parser.parse_args()
    changelog = CHANGELOG.read_text()
    try:
        current = source_protocol((ROOT / HOOK_SOURCE).read_text())
        if args.check:
            check(changelog)
            sys.stderr.write("CHANGELOG.md entries are well-formed.\n")
            return 0
        match = TAG.match(args.tag or "")
        if match is None:
            raise ReleaseError(f"{args.tag!r} is not a release tag like v1.2.0")
        previous_tag, previous = previous_release(args.tag)
        sys.stdout.write(
            notes(
                match.group(1),
                changelog,
                current,
                previous_tag=previous_tag,
                previous=previous,
            )
        )
    except ReleaseError as exc:
        sys.stderr.write(f"{exc}\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
