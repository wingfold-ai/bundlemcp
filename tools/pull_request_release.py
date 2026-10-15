#!/usr/bin/env python3
"""The release a pull request carries: its labels, its version and its changelog entry.

    python3 tools/pull_request_release.py labels "feat(bundles): Order members by hand"
    python3 tools/pull_request_release.py apply --title ... --number 140 --url ... [--text FILE]
    python3 tools/pull_request_release.py text-status [--bot-ref SHA]

``labels`` prints the ``type:`` and ``semver:`` labels a Conventional Commit
title derives, or fails naming the expected form. ``apply`` rewrites
CHANGELOG.md and the version files of the checked-out branch to the base
branch's content plus this pull request's entry and version bump; it prints the
version, or nothing when the title releases nothing. ``text-status`` says
whether the branch's entry text is missing, still the one CI last wrote, or
edited by someone since.

The entry's text comes from ``--text`` or, without it, from the entry already on
the branch, so renumbering never rewrites wording.
"""

import argparse
import datetime
import re
import subprocess
import sys
from pathlib import Path

from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
CHANGELOG = "CHANGELOG.md"
HOOK_SOURCE = "packages/bundlemcp/bundlemcp/application/metering/metering_hook.py"
PACKAGE_PYPROJECT = "packages/bundlemcp/pyproject.toml"
MAX_TITLE = 72

TITLE = re.compile(
    r"^(?P<type>feat|fix|perf|refactor|docs|test|build|ci|chore|revert)"
    r"(?:\((?P<scope>[a-z0-9][a-z0-9-]*)\))?(?P<breaking>!)?: (?P<subject>\S.*)$"
)
EXPECTED = "<type>(<scope>)!: <Subject>, e.g. 'feat(bundles): Order members by hand'"
BUMPS = {"feat": "minor", "fix": "patch", "perf": "patch", "revert": "patch"}
SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
ENTRY = re.compile(r"^## \[(\d+\.\d+\.\d+)\][^\n]*\n", re.MULTILINE)
SECOND_LEVEL = re.compile(r"^## ", re.MULTILINE)
PROTOCOL_LINE = re.compile(r"^Metering-hook protocol: \d+\s*\n?", re.MULTILINE)
SOURCE_PROTOCOL = re.compile(r"^METERING_PROTOCOL_VERSION = (\d+)", re.MULTILINE)

# Where each version file states the version: the pattern's first group is kept,
# the version follows it.
VERSION_SITES = {
    "pyproject.toml": re.compile(
        r'(\A\[project\]\nname = "bundlemcp-workspace"\nversion = ")[^"]+'
    ),
    PACKAGE_PYPROJECT: re.compile(r'(\A\[project\]\nname = "bundlemcp"\nversion = ")[^"]+'),
    "uv.lock": re.compile(r'(\nname = "bundlemcp(?:-workspace)?"\nversion = ")[^"]+'),
    "apps/web/openapi.json": re.compile(
        r'("info": \{\n\s*"title": "bundlemcp",\n\s*"version": ")[^"]+'
    ),
}


class ReleaseError(Exception):
    """The pull request cannot carry a release as asked."""


class TitleRelease(BaseModel):
    """What a pull request title says about the release its merge makes."""

    type: str = Field(description="Conventional Commit type, e.g. 'feat'")
    breaking: bool = Field(description="Whether the title marks a breaking change with '!'")
    subject: str = Field(description="The title after the colon")
    bump: str = Field(
        pattern=r"^(major|minor|patch|none)$",
        description="Semantic version bump: 'major', 'minor', 'patch' or 'none'",
    )

    @property
    def labels(self) -> list[str]:
        return [f"type: {self.type}", f"semver: {self.bump}"]


def parse_title(title: str) -> TitleRelease:
    """The release a title derives; a title that is no Conventional Commit is refused."""
    if len(title) > MAX_TITLE:
        raise ReleaseError(f"the title is {len(title)} characters; keep it within {MAX_TITLE}")
    match = TITLE.match(title)
    if match is None:
        raise ReleaseError(f"the title is no Conventional Commit; expected {EXPECTED}")
    breaking = match.group("breaking") is not None
    kind = match.group("type")
    return TitleRelease(
        type=kind,
        breaking=breaking,
        subject=match.group("subject"),
        bump="major" if breaking else BUMPS.get(kind, "none"),
    )


def next_version(current: str, bump: str) -> str:
    """``current`` raised by ``bump``; below 1.0 every bump moves one place to the right."""
    match = SEMVER.match(current)
    if match is None:
        raise ReleaseError(f"{current!r} is not a version like 1.2.0")
    major, minor, patch = (int(part) for part in match.groups())
    if bump == "none":
        return current
    if major == 0:
        bump = "minor" if bump == "major" else "patch"
    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def released_versions(changelog: str) -> set[str]:
    return set(ENTRY.findall(changelog))


def entry_text(changelog: str, base: str) -> str | None:
    """The text of the one entry ``changelog`` has and ``base`` lacks, minus its protocol line."""
    known = released_versions(base)
    for match in ENTRY.finditer(changelog):
        if match.group(1) in known:
            continue
        following = SECOND_LEVEL.search(changelog, match.end())
        end = following.start() if following else len(changelog)
        return PROTOCOL_LINE.sub("", changelog[match.end() : end], count=1).strip()
    return None


def without_unreleased(changelog: str, base: str) -> str:
    """``changelog`` without the entries ``base`` does not have: the ones CI added to the branch."""
    known = released_versions(base)
    for match in reversed(list(ENTRY.finditer(changelog))):
        if match.group(1) in known:
            continue
        following = SECOND_LEVEL.search(changelog, match.end())
        end = following.start() if following else len(changelog)
        changelog = changelog[: match.start()] + changelog[end:]
    return changelog


def with_entry(changelog: str, version: str, date: str, protocol: int, text: str) -> str:
    """``changelog`` with the entry inserted above its newest entry, or above its first section."""
    entry = f"## [{version}] - {date}\n\nMetering-hook protocol: {protocol}\n\n{text.strip()}\n\n"
    first = ENTRY.search(changelog) or SECOND_LEVEL.search(changelog)
    at = first.start() if first else len(changelog)
    return changelog[:at] + entry + changelog[at:]


def set_version(content: str, path: str, version: str) -> str:
    pattern = VERSION_SITES[path]
    updated, count = pattern.subn(lambda match: match.group(1) + version, content)
    if count == 0:
        raise ReleaseError(f"no version found in {path}")
    return updated


def project_version(pyproject: str) -> str:
    match = VERSION_SITES[PACKAGE_PYPROJECT].search(pyproject)
    if match is None:
        raise ReleaseError(f"no version found in {PACKAGE_PYPROJECT}")
    return pyproject[match.end(1) : match.end()]


def source_protocol(source: str) -> int:
    match = SOURCE_PROTOCOL.search(source)
    if match is None:
        raise ReleaseError(f"no METERING_PROTOCOL_VERSION in {HOOK_SOURCE}")
    return int(match.group(1))


def fallback_text(release: TitleRelease, number: int, url: str) -> str:
    """The entry text when no written one is available: the subject under its type's section."""
    section = {"feat": "Added", "fix": "Fixed"}.get(release.type, "Changed")
    marker = "**Breaking:** " if release.breaking else ""
    return f"### {section}\n\n- {marker}{release.subject} ([#{number}]({url}))"


def _git(*args: str, cwd: Path) -> str:
    done = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if done.returncode != 0:
        raise ReleaseError(f"git {' '.join(args)} failed: {done.stderr.strip()}")
    return done.stdout


def _changelog_at(tree: Path, ref: str) -> str:
    return _git("show", f"{ref}:{CHANGELOG}", cwd=tree)


def _merge_base(tree: Path, ref: str, base_ref: str) -> str:
    return _git("merge-base", ref, base_ref, cwd=tree).strip()


def branch_entry_text(tree: Path, base_ref: str, ref: str | None = None) -> str | None:
    """The entry text the branch (or ``ref``) adds over the base it was last brought up to."""
    seen = _changelog_at(tree, _merge_base(tree, ref or "HEAD", base_ref))
    current = _changelog_at(tree, ref) if ref else (tree / CHANGELOG).read_text()
    return entry_text(current, seen)


def merge_base_branch(tree: Path, base_ref: str) -> None:
    """Merge ``base_ref`` into the branch; the files ``apply`` rewrites take the base's side."""
    contained = subprocess.run(["git", "merge-base", "--is-ancestor", base_ref, "HEAD"], cwd=tree)
    if contained.returncode == 0:
        return
    owned = {CHANGELOG, *VERSION_SITES}
    merged = subprocess.run(
        ["git", "merge", "--no-edit", base_ref], cwd=tree, capture_output=True, text=True
    )
    if merged.returncode == 0:
        return
    conflicted = set(_git("diff", "--name-only", "--diff-filter=U", cwd=tree).split())
    if not conflicted or not conflicted <= owned:
        subprocess.run(["git", "merge", "--abort"], cwd=tree)
        others = ", ".join(sorted(conflicted - owned)) or merged.stderr.strip()
        raise ReleaseError(f"merging {base_ref} conflicts in {others}; the author resolves it")
    _git("checkout", "--theirs", "--", *sorted(conflicted), cwd=tree)
    _git("add", "--", *sorted(conflicted), cwd=tree)
    _git("commit", "--no-edit", cwd=tree)


def apply(
    tree: Path,
    base_ref: str,
    release: TitleRelease,
    *,
    number: int,
    url: str,
    date: str,
    text: str | None,
) -> str | None:
    """Bring the branch up to the base, then write its entry and bump; the version, or None.

    The branch's own edits to the changelog outside its entry are kept. Without
    ``text`` the entry keeps the text it already has on the branch, read before
    the merge, so renumbering never changes wording.
    """
    if text is None:
        text = branch_entry_text(tree, base_ref)
    merge_base_branch(tree, base_ref)
    base_changelog = _changelog_at(tree, base_ref)
    base_version = project_version(_git("show", f"{base_ref}:{PACKAGE_PYPROJECT}", cwd=tree))
    version = next_version(base_version, release.bump)
    changelog_path = tree / CHANGELOG
    changelog = without_unreleased(changelog_path.read_text(), base_changelog)
    if release.bump != "none":
        protocol = source_protocol((tree / HOOK_SOURCE).read_text())
        text = text or fallback_text(release, number, url)
        changelog = with_entry(changelog, version, date, protocol, text)
    changelog_path.write_text(changelog)
    for path in VERSION_SITES:
        file = tree / path
        file.write_text(set_version(file.read_text(), path, version))
    return None if release.bump == "none" else version


def text_status(tree: Path, base_ref: str, bot_ref: str | None) -> str:
    """``missing``, ``generated`` (as CI last wrote it) or ``edited`` (changed by someone since)."""
    current = branch_entry_text(tree, base_ref)
    if not current:
        return "missing"
    if bot_ref is None:
        return "edited"
    return "generated" if branch_entry_text(tree, base_ref, bot_ref) == current else "edited"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    labels = commands.add_parser("labels", help="Print the labels a title derives")
    labels.add_argument("title")
    applying = commands.add_parser("apply", help="Write the entry and the bump")
    applying.add_argument("--title", required=True)
    applying.add_argument("--number", type=int, required=True)
    applying.add_argument("--url", required=True)
    applying.add_argument("--date", default=datetime.datetime.now(datetime.UTC).date().isoformat())
    applying.add_argument("--base-ref", default="origin/main")
    applying.add_argument("--text", type=Path, help="File with the entry's text")
    status = commands.add_parser("text-status", help="Whether the entry text was edited")
    status.add_argument("--base-ref", default="origin/main")
    status.add_argument("--bot-ref", help="CI's newest commit on the branch")
    args = parser.parse_args()
    try:
        if args.command == "labels":
            sys.stdout.write("\n".join(parse_title(args.title).labels) + "\n")
        elif args.command == "apply":
            version = apply(
                ROOT,
                args.base_ref,
                parse_title(args.title),
                number=args.number,
                url=args.url,
                date=args.date,
                text=args.text.read_text() if args.text else None,
            )
            sys.stdout.write(f"{version}\n" if version else "")
        else:
            sys.stdout.write(text_status(ROOT, args.base_ref, args.bot_ref) + "\n")
    except ReleaseError as exc:
        sys.stderr.write(f"{exc}\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
