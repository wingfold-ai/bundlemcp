#!/usr/bin/env python3
"""Release notes from CHANGELOG.md, stating the metering-hook protocol version.

    python3 tools/release_notes.py v1.2.0      # the notes for that tag, on stdout
    python3 tools/release_notes.py --check     # every entry names a protocol version,
                                               # and the newest names the current one

Fails (exit 1) when the changelog has no entry for the version, when an entry
does not name the metering-hook protocol version, or when the entry for the
version names another one than the source does. The notes end with that
version and whether it changed since the previous release tag.
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
SECTION = re.compile(r"^## ", re.MULTILINE)
PROTOCOL_LINE = re.compile(r"^Metering-hook protocol: (\d+)\s*$", re.MULTILINE)
SOURCE_VERSION = re.compile(r"^METERING_PROTOCOL_VERSION = (\d+)", re.MULTILINE)
VERSIONING = "https://bundlemcp.com/integrate/metering-hook#versioning"


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


def protocol_of(entry: str, name: str) -> int:
    match = PROTOCOL_LINE.search(entry)
    if match is None:
        raise ReleaseError(f"changelog entry {name} does not say 'Metering-hook protocol: <n>'")
    return int(match.group(1))


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
    stated = protocol_of(entry, version)
    if stated != current:
        raise ReleaseError(
            f"changelog entry {version} names metering-hook protocol {stated}, the source {current}"
        )
    body = PROTOCOL_LINE.sub("", entry).strip()
    if previous_tag is None or previous is None:
        protocol = f"Metering-hook protocol version: **{current}**."
    elif previous == current:
        protocol = f"Metering-hook protocol version: **{current}**, unchanged since {previous_tag}."
    else:
        protocol = (
            f"Metering-hook protocol version: **{current}**, **changed** from {previous} in "
            f"{previous_tag}. Hooks must be updated; see {VERSIONING}."
        )
    return f"{body}\n\n---\n\n{protocol}\n"


def check(changelog: str, current: int) -> None:
    """Every entry names a protocol version, and the newest names the current one."""
    found = entries(changelog)
    if not found:
        raise ReleaseError("CHANGELOG.md has no entries")
    for name, entry in found.items():
        protocol_of(entry, name)
    newest = next(iter(found))
    if protocol_of(found[newest], newest) != current:
        raise ReleaseError(
            f"the newest changelog entry ({newest}) must name metering-hook protocol {current}"
        )


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
            check(changelog, current)
            sys.stderr.write(f"CHANGELOG.md names metering-hook protocol {current}.\n")
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
