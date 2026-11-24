#!/usr/bin/env python3
"""Audit the locked Python and npm dependencies against the public advisory databases.

    uv run python tools/check_advisories.py

The Python audit exports the whole workspace lock (every package, group and
extra, development tools included), and the lock of each standalone Python
project an image installs, and hands each to pip-audit; every reported
vulnerability counts, since Python advisories rarely carry a severity. The npm
audit reads the lockfiles of apps/web and docs, development dependencies
included; an advisory of moderate severity or above counts, a low or info one
does not.

An advisory no release fixes yet may be accepted in tools/advisory_allowlist.toml,
with a reason and an expiry at most 90 days ahead. An expired entry, or one dated
further ahead, fails the check whether or not its advisory is still reported; an
entry that matches nothing is printed as removable and does not fail.

Exit status: 0 when nothing counted is left, 1 on a finding or an allow-list
entry that fails, 2 when an audit could not run at all (for example, the
advisory database was unreachable): re-run it, nothing was judged.
"""

import argparse
import datetime
import json
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

ROOT = Path(__file__).resolve().parents[1]
ALLOWLIST = ROOT / "tools" / "advisory_allowlist.toml"
NPM_PROJECTS = ("apps/web", "docs")
NPM_COUNTED_SEVERITIES = frozenset({"moderate", "high", "critical"})
MAX_ALLOWLIST_DAYS = 90
PYTHON_EXPORT = [
    "uv",
    "export",
    "--locked",
    "--all-packages",
    "--all-groups",
    "--all-extras",
    "--no-hashes",
    "--no-emit-workspace",
]
# Python projects outside the workspace with a lock of their own, which an image installs
PYTHON_STANDALONE_PROJECTS = ("deploy/glama/bridge",)
PYTHON_STANDALONE_EXPORT = [
    "uv",
    "export",
    "--locked",
    "--all-groups",
    "--all-extras",
    "--no-hashes",
    "--no-emit-project",
]
FIX_HINT = (
    "upgrade it; if no release fixes it yet, list it in tools/advisory_allowlist.toml "
    "with a reason and an expiry at most 90 days ahead"
)


class AuditNotRun(Exception):
    """An audit could not produce a report, so nothing was judged."""


class Advisory(BaseModel):
    """One advisory reported against one locked package."""

    model_config = ConfigDict(frozen=True)

    ecosystem: Literal["python", "npm"] = Field(description="Which audit reported it")
    source: str = Field(description="The lockfile's project: 'uv.lock', 'apps/web' or 'docs'")
    package: str = Field(description="The affected package's name")
    version: str = Field(
        description="The locked version (Python) or the affected range npm reports (npm)"
    )
    id: str = Field(description="The advisory's identifier, e.g. 'GHSA-gcqx-w48m-w2h4'")
    aliases: tuple[str, ...] = Field(
        default=(), description="Other identifiers of the same advisory, e.g. a CVE"
    )
    severity: str | None = Field(
        default=None, description="npm's severity; None for Python, whose reports carry none"
    )

    @property
    def counts(self) -> bool:
        """Whether this advisory fails the check unless an allow-list entry accepts it."""
        return self.severity is None or self.severity in NPM_COUNTED_SEVERITIES

    def describe(self) -> str:
        severity = f", {self.severity}" if self.severity else ""
        return f"{self.package} {self.version} has {self.id}{severity} ({self.source})"


class AllowlistEntry(BaseModel):
    """An advisory accepted for now, because no release fixes it yet."""

    id: str = Field(
        pattern=r"^(GHSA(-[23456789cfghjmpqrvwx]{4}){3}|PYSEC-\d{4}-\d+|CVE-\d{4}-\d{4,})$",
        description="The advisory's identifier: a GHSA, PYSEC or CVE id",
    )
    package: str = Field(min_length=1, description="The affected package, as the audit names it")
    reason: str = Field(
        min_length=1, description="Why the advisory does not reach bundlemcp, or what limits it"
    )
    expires: datetime.date = Field(
        description="The day the acceptance ends; at most 90 days after the day it is checked"
    )

    def matches(self, advisory: Advisory) -> bool:
        same_package = self.package.lower() == advisory.package.lower()
        return same_package and (self.id == advisory.id or self.id in advisory.aliases)

    def describe(self) -> str:
        return f"{self.id} for {self.package} (expires {self.expires.isoformat()})"


class Allowlist(BaseModel):
    """The reviewed list of accepted advisories, as tools/advisory_allowlist.toml holds it."""

    advisory: list[AllowlistEntry] = Field(
        default_factory=list, description="Every accepted advisory"
    )


class AcceptedAdvisory(BaseModel):
    """A counted advisory and the allow-list entry that accepts it."""

    advisory: Advisory = Field(description="The reported advisory")
    entry: AllowlistEntry = Field(description="The entry that accepts it")


class Verdict(BaseModel):
    """What the audits found, judged against the allow-list on one day."""

    failing: list[Advisory] = Field(description="Counted advisories no valid entry accepts")
    accepted: list[AcceptedAdvisory] = Field(description="Counted advisories an entry accepts")
    below_bar: list[Advisory] = Field(description="npm advisories below moderate severity")
    expired: list[AllowlistEntry] = Field(description="Entries whose expiry has passed")
    too_far: list[AllowlistEntry] = Field(description="Entries dated more than 90 days ahead")
    removable: list[AllowlistEntry] = Field(description="Entries that match no advisory")

    @property
    def passed(self) -> bool:
        return not (self.failing or self.expired or self.too_far)


def python_advisories(report: dict[str, Any], source: str = "uv.lock") -> list[Advisory]:
    """Every vulnerability in a ``pip-audit --format json`` report.

    A dependency pip-audit skipped was not audited, which the check cannot vouch
    for, so it is reported as an audit that did not run.
    """
    skipped = [d for d in report.get("dependencies", []) if d.get("skip_reason")]
    if skipped:
        names = ", ".join(f"{d['name']} ({d['skip_reason']})" for d in skipped)
        raise AuditNotRun(f"pip-audit could not audit: {names}")
    return [
        Advisory(
            ecosystem="python",
            source=source,
            package=dependency["name"],
            version=dependency["version"],
            id=vuln["id"],
            aliases=tuple(vuln.get("aliases", ())),
        )
        for dependency in report.get("dependencies", [])
        for vuln in dependency.get("vulns", [])
    ]


def npm_advisories(report: dict[str, Any], project: str) -> list[Advisory]:
    """Every advisory in an ``npm audit --json`` report, once per package and advisory.

    npm lists a package that is vulnerable only through a dependency with that
    dependency's name instead of an advisory; only the advisories themselves are
    kept, so a chain is reported once, at the package it is about.
    """
    if "error" in report:
        raise AuditNotRun(f"npm audit in {project}: {report['error'].get('summary', 'failed')}")
    found: dict[tuple[str, str], Advisory] = {}
    for vulnerability in report.get("vulnerabilities", {}).values():
        for via in vulnerability.get("via", []):
            if not isinstance(via, dict):
                continue
            advisory_id = str(via.get("url", "")).rstrip("/").rsplit("/", 1)[-1]
            advisory = Advisory(
                ecosystem="npm",
                source=project,
                package=via["name"],
                version=via.get("range", vulnerability.get("range", "")),
                id=advisory_id or str(via["source"]),
                severity=via["severity"],
            )
            found.setdefault((advisory.package, advisory.id), advisory)
    return list(found.values())


def evaluate(advisories: list[Advisory], allowlist: Allowlist, today: datetime.date) -> Verdict:
    """Judge the reported advisories against the allow-list as it stands on ``today``."""
    horizon = today + datetime.timedelta(days=MAX_ALLOWLIST_DAYS)
    expired = [e for e in allowlist.advisory if e.expires < today]
    too_far = [e for e in allowlist.advisory if e.expires > horizon]
    valid = [e for e in allowlist.advisory if today <= e.expires <= horizon]
    failing: list[Advisory] = []
    accepted: list[AcceptedAdvisory] = []
    for advisory in (a for a in advisories if a.counts):
        entry = next((e for e in valid if e.matches(advisory)), None)
        if entry is None:
            failing.append(advisory)
        else:
            accepted.append(AcceptedAdvisory(advisory=advisory, entry=entry))
    removable = [
        e for e in allowlist.advisory if not any(e.matches(a) for a in advisories if a.counts)
    ]
    return Verdict(
        failing=failing,
        accepted=accepted,
        below_bar=[a for a in advisories if not a.counts],
        expired=expired,
        too_far=too_far,
        removable=removable,
    )


def load_allowlist(path: Path) -> Allowlist:
    return Allowlist.model_validate(tomllib.loads(path.read_text()))


def run_python_audit(project: str = "") -> dict[str, Any]:
    """pip-audit's report on the workspace lock, or on ``project``'s own lock."""
    command = PYTHON_STANDALONE_EXPORT if project else PYTHON_EXPORT
    export = subprocess.run(command, cwd=ROOT / project, capture_output=True, text=True)
    if export.returncode != 0:
        raise AuditNotRun(f"uv export failed in {project or '.'}: {export.stderr.strip()}")
    audit = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip_audit",
            "--requirement",
            "/dev/stdin",
            "--no-deps",
            "--disable-pip",
            "--progress-spinner",
            "off",
            "--format",
            "json",
        ],
        cwd=ROOT,
        input=export.stdout,
        capture_output=True,
        text=True,
    )
    try:
        return json.loads(audit.stdout)
    except json.JSONDecodeError:
        raise AuditNotRun(f"pip-audit produced no report: {audit.stderr.strip()}") from None


def run_npm_audit(project: str) -> dict[str, Any]:
    audit = subprocess.run(
        ["npm", "audit", "--package-lock-only", "--json"],
        cwd=ROOT / project,
        capture_output=True,
        text=True,
    )
    try:
        return json.loads(audit.stdout)
    except json.JSONDecodeError:
        raise AuditNotRun(
            f"npm audit in {project} produced no report: {audit.stderr.strip()}"
        ) from None


def report(verdict: Verdict) -> list[str]:
    """The lines the check prints for ``verdict``, failures first."""
    lines = [f"DEP-14: {a.describe()}: {FIX_HINT}" for a in verdict.failing]
    lines += [
        f"DEP-14: allow-list entry {e.describe()} has expired: re-decide it, then renew or "
        "remove it"
        for e in verdict.expired
    ]
    lines += [
        f"DEP-14: allow-list entry {e.describe()} is more than {MAX_ALLOWLIST_DAYS} days ahead"
        for e in verdict.too_far
    ]
    lines += [
        f"accepted: {item.advisory.describe()}, until {item.entry.expires.isoformat()}: "
        f"{item.entry.reason}"
        for item in verdict.accepted
    ]
    lines += [f"below the bar: {a.describe()}" for a in verdict.below_bar]
    lines += [
        f"removable: allow-list entry {e.describe()} matches nothing" for e in verdict.removable
    ]
    return lines


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--today",
        type=datetime.date.fromisoformat,
        default=datetime.datetime.now(datetime.UTC).date(),
        help="judge the allow-list as on this day (YYYY-MM-DD); defaults to today in UTC",
    )
    args = parser.parse_args(argv)
    try:
        allowlist = load_allowlist(ALLOWLIST)
    except (tomllib.TOMLDecodeError, ValidationError) as error:
        sys.stderr.write(f"DEP-14: {ALLOWLIST.relative_to(ROOT)} is malformed: {error}\n")
        return 1
    try:
        advisories = python_advisories(run_python_audit())
        for project in PYTHON_STANDALONE_PROJECTS:
            advisories += python_advisories(run_python_audit(project), f"{project}/uv.lock")
        for project in NPM_PROJECTS:
            advisories += npm_advisories(run_npm_audit(project), project)
    except AuditNotRun as error:
        sys.stderr.write(
            f"The advisory audit did not run, so nothing was judged: {error}\n"
            "This is not a finding; re-run the check.\n"
        )
        return 2
    verdict = evaluate(advisories, allowlist, args.today)
    lines = report(verdict)
    if lines:
        sys.stderr.write("\n".join(lines) + "\n")
    if not verdict.passed:
        return 1
    sys.stderr.write(
        "No advisory at or above the bar in uv.lock, "
        + ", ".join(f"{p}/uv.lock" for p in PYTHON_STANDALONE_PROJECTS)
        + ", "
        + " or ".join(f"{p}/package-lock.json" for p in NPM_PROJECTS)
        + f" ({len(verdict.accepted)} accepted).\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
