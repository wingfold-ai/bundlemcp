"""The dependency advisory check and its allow-list, over recorded audit reports (DEP-14)."""

import datetime
import importlib.util
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[4]
_spec = importlib.util.spec_from_file_location(
    "check_advisories", ROOT / "tools/check_advisories.py"
)
assert _spec is not None and _spec.loader is not None
advisories = importlib.util.module_from_spec(_spec)
sys.modules["check_advisories"] = advisories
_spec.loader.exec_module(advisories)

TODAY = datetime.date(2026, 10, 29)

# pip-audit --format json over a lock holding urllib3 2.2.1, trimmed to one advisory
PIP_AUDIT_URLLIB3 = {
    "dependencies": [
        {"name": "certifi", "version": "2026.10.19", "vulns": []},
        {
            "name": "urllib3",
            "version": "2.2.1",
            "vulns": [
                {
                    "id": "PYSEC-2026-1995",
                    "fix_versions": ["1.26.19", "2.2.2"],
                    "aliases": ["CVE-2024-37891", "GHSA-34jh-p97f-mpxf"],
                    "description": "When using urllib3's proxy support with `ProxyManager`",
                }
            ],
        },
    ],
    "fixes": [],
}
PIP_AUDIT_CLEAN = {
    "dependencies": [{"name": "certifi", "version": "2026.10.19", "vulns": []}],
    "fixes": [],
}

# npm audit --package-lock-only --json in docs, before vite 6.4.5 was locked
NPM_DOCS_VITE = {
    "vulnerabilities": {
        "vite": {
            "name": "vite",
            "severity": "moderate",
            "isDirect": False,
            "via": [
                {
                    "source": 1243858,
                    "name": "vite",
                    "dependency": "vite",
                    "title": "Vite: `server.fs.deny` bypassed with queries",
                    "url": "https://github.com/advisories/GHSA-8g5g-mxqh-grgj",
                    "severity": "moderate",
                    "range": "=6.4.4",
                }
            ],
            "effects": [],
            "range": "6.4.4",
            "nodes": ["node_modules/vite"],
            "fixAvailable": True,
        }
    }
}

# npm audit --package-lock-only --json in apps/web on 2026-10-29: one low advisory, reported
# through the chain that pulls it in
NPM_WEB_DEEPMERGE = {
    "vulnerabilities": {
        "@rollup/plugin-node-resolve": {
            "name": "@rollup/plugin-node-resolve",
            "severity": "low",
            "via": ["deepmerge"],
            "range": ">=8.0.0",
        },
        "deepmerge": {
            "name": "deepmerge",
            "severity": "low",
            "via": [
                {
                    "source": 1243505,
                    "name": "deepmerge",
                    "dependency": "deepmerge",
                    "title": "deepmerge mergeObject() allows prototype poisoning",
                    "url": "https://github.com/advisories/GHSA-gcqx-w48m-w2h4",
                    "severity": "low",
                    "range": ">=4.2.0 <=4.3.1",
                }
            ],
            "range": ">=4.2.0",
        },
        "nitropack": {
            "name": "nitropack",
            "severity": "low",
            "via": ["@rollup/plugin-node-resolve"],
            "range": ">=2.0.0",
        },
        "nuxt": {
            "name": "nuxt",
            "severity": "low",
            "via": ["@nuxt/nitro-server", "@nuxt/vite-builder", "@nuxt/vite-server"],
            "range": "3.20.0 - 3.21.11 || >=4.2.0",
        },
    }
}


def entry(**overrides: object) -> object:
    values = {
        "id": "GHSA-8g5g-mxqh-grgj",
        "package": "vite",
        "reason": "Dev server only; the docs site is built, never served by vite",
        "expires": TODAY + datetime.timedelta(days=30),
    }
    return advisories.AllowlistEntry(**{**values, **overrides})


def allowlist(*entries: object) -> object:
    return advisories.Allowlist(advisory=list(entries))


def test_dep14_python_finding_fails():
    """DEP-14: a vulnerability pip-audit reports in the lock fails, naming package, version
    and advisory."""
    found = advisories.python_advisories(PIP_AUDIT_URLLIB3)
    verdict = advisories.evaluate(found, allowlist(), TODAY)
    assert not verdict.passed
    assert [a.describe() for a in verdict.failing] == [
        "urllib3 2.2.1 has PYSEC-2026-1995 (uv.lock)"
    ]
    assert advisories.report(verdict)[0].startswith("DEP-14: urllib3 2.2.1 has PYSEC-2026-1995")


def test_dep14_clean_python_lock_passes():
    """DEP-14: a lock with no reported vulnerability passes."""
    verdict = advisories.evaluate(advisories.python_advisories(PIP_AUDIT_CLEAN), allowlist(), TODAY)
    assert verdict.passed


def test_dep14_skipped_python_dependency_is_not_a_pass():
    """DEP-14: a dependency pip-audit could not audit stops the check instead of passing it."""
    report = {"dependencies": [{"name": "private-pkg", "skip_reason": "not found on PyPI"}]}
    with pytest.raises(advisories.AuditNotRun, match="private-pkg"):
        advisories.python_advisories(report)


def test_dep14_moderate_npm_advisory_fails():
    """DEP-14: a moderate npm advisory in a development dependency fails, naming it."""
    found = advisories.npm_advisories(NPM_DOCS_VITE, "docs")
    verdict = advisories.evaluate(found, allowlist(), TODAY)
    assert not verdict.passed
    assert [a.describe() for a in verdict.failing] == [
        "vite =6.4.4 has GHSA-8g5g-mxqh-grgj, moderate (docs)"
    ]


def test_dep14_low_npm_advisory_passes():
    """DEP-14: today's low deepmerge advisory in apps/web is reported once, below the bar."""
    found = advisories.npm_advisories(NPM_WEB_DEEPMERGE, "apps/web")
    verdict = advisories.evaluate(found, allowlist(), TODAY)
    assert verdict.passed
    assert [(a.package, a.id) for a in verdict.below_bar] == [("deepmerge", "GHSA-gcqx-w48m-w2h4")]


def test_dep14_npm_report_without_a_result_is_not_a_pass():
    """DEP-14: an npm audit that could not reach the registry stops the check."""
    report = {"error": {"code": "ENOTFOUND", "summary": "request to registry failed"}}
    with pytest.raises(advisories.AuditNotRun, match="registry"):
        advisories.npm_advisories(report, "docs")


def test_dep14_allowlisted_advisory_passes():
    """DEP-14: a listed advisory before its expiry passes and is reported as accepted."""
    found = advisories.npm_advisories(NPM_DOCS_VITE, "docs")
    verdict = advisories.evaluate(found, allowlist(entry()), TODAY)
    assert verdict.passed
    assert [item.advisory.id for item in verdict.accepted] == ["GHSA-8g5g-mxqh-grgj"]
    assert any(line.startswith("accepted: vite") for line in advisories.report(verdict))


def test_dep14_allowlist_matches_an_alias():
    """DEP-14: an entry naming the advisory's GHSA accepts the PYSEC id pip-audit reports."""
    found = advisories.python_advisories(PIP_AUDIT_URLLIB3)
    listed = entry(id="GHSA-34jh-p97f-mpxf", package="urllib3")
    assert advisories.evaluate(found, allowlist(listed), TODAY).passed


def test_dep14_allowlist_entry_for_another_package_does_not_accept():
    """DEP-14: an entry accepts an advisory only for the package it names."""
    found = advisories.npm_advisories(NPM_DOCS_VITE, "docs")
    verdict = advisories.evaluate(found, allowlist(entry(package="rollup")), TODAY)
    assert not verdict.passed


def test_dep14_expired_entry_fails():
    """DEP-14: an entry past its expiry fails, whether or not its advisory is still reported."""
    stale = entry(expires=TODAY - datetime.timedelta(days=1))
    for found in ([], advisories.npm_advisories(NPM_DOCS_VITE, "docs")):
        verdict = advisories.evaluate(found, allowlist(stale), TODAY)
        assert not verdict.passed
        assert verdict.expired == [stale]
        assert any("has expired" in line for line in advisories.report(verdict))


def test_dep14_entry_expiring_today_is_still_valid():
    """DEP-14: an entry is valid through its expiry day."""
    found = advisories.npm_advisories(NPM_DOCS_VITE, "docs")
    assert advisories.evaluate(found, allowlist(entry(expires=TODAY)), TODAY).passed


def test_dep14_entry_beyond_90_days_fails():
    """DEP-14: an entry dated more than 90 days ahead fails and is named; 90 days is allowed."""
    found = advisories.npm_advisories(NPM_DOCS_VITE, "docs")
    at_limit = entry(expires=TODAY + datetime.timedelta(days=90))
    beyond = entry(expires=TODAY + datetime.timedelta(days=91))
    assert advisories.evaluate(found, allowlist(at_limit), TODAY).passed
    verdict = advisories.evaluate(found, allowlist(beyond), TODAY)
    assert not verdict.passed
    assert verdict.too_far == [beyond]
    assert any("more than 90 days ahead" in line for line in advisories.report(verdict))


def test_dep14_unmatched_entry_only_warns():
    """DEP-14: an entry no advisory matches is printed as removable and does not fail."""
    verdict = advisories.evaluate([], allowlist(entry()), TODAY)
    assert verdict.passed
    assert verdict.removable == [entry()]
    assert advisories.report(verdict) == [
        "removable: allow-list entry GHSA-8g5g-mxqh-grgj for vite (expires 2026-11-28) "
        "matches nothing"
    ]


def test_dep14_allowlist_entry_needs_id_reason_and_expiry():
    """DEP-14: an entry without a reason, or with an id that is no advisory id, is refused."""
    with pytest.raises(ValueError):
        entry(reason="")
    with pytest.raises(ValueError):
        entry(id="deepmerge")


def test_dep14_committed_allowlist_is_well_formed():
    """DEP-14: the repository's allow-list parses; whether its entries are in date is the
    check's own job, so this test does not depend on the day it runs."""
    listed = advisories.load_allowlist(ROOT / "tools/advisory_allowlist.toml")
    assert all(item.reason for item in listed.advisory)
