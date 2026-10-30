"""The gates CI runs: ruff's security rules, installs from the lock, one required check."""

import pathlib
import re
import tomllib

ROOT = pathlib.Path(__file__).resolve().parents[4]
LIBRARY = ROOT / "packages" / "bundlemcp" / "bundlemcp"
CI = ROOT / ".github" / "workflows" / "ci.yml"

UV_SYNC = re.compile(r"\buv sync\b[^\n]*")
JOB = re.compile(r"^  (?P<name>[A-Za-z0-9_-]+):\s*$")
NEEDS = re.compile(r"^    needs:\s*\[(?P<jobs>[^\]]*)\]")


def ruff_lint() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["ruff"]["lint"]


def security_rule_gaps(lint: dict, library_files: list[str]) -> list[str]:
    """What keeps ruff's security rules from covering the library, or nothing."""
    gaps = [] if "S" in lint.get("select", []) else ["'S' is not in [tool.ruff.lint] select"]
    for pattern, rules in lint.get("per-file-ignores", {}).items():
        if not any(rule.startswith("S") for rule in rules):
            continue
        matched = [f for f in library_files if pathlib.PurePosixPath(f).full_match(pattern)]
        if matched:
            gaps.append(f"per-file ignore {pattern!r} covers library files, e.g. {matched[0]}")
    return gaps


def library_files() -> list[str]:
    return sorted(str(p.relative_to(ROOT)) for p in LIBRARY.rglob("*.py"))


def test_dep14_ruff_security_rules_cover_the_library():
    """DEP-14: ruff selects the S rules, and no per-file ignore exempts library code."""
    gaps = security_rule_gaps(ruff_lint(), library_files())
    assert library_files()
    assert not gaps, "DEP-14: " + "; ".join(gaps)


def test_dep14_the_check_catches_a_weakened_configuration():
    """DEP-14: dropping 'S' from select, or ignoring it for the library, is reported."""
    files = ["packages/bundlemcp/bundlemcp/domain/shared/secrets.py"]
    lint = ruff_lint()
    without_s = {**lint, "select": [r for r in lint["select"] if r != "S"]}
    assert security_rule_gaps(without_s, files)
    library_ignore = {**lint, "per-file-ignores": {"packages/**": ["S105"]}}
    assert security_rule_gaps(library_ignore, files)
    assert not security_rule_gaps(lint, files)


def unlocked_syncs(text: str) -> list[str]:
    """Every ``uv sync`` command in ``text`` that does not carry ``--locked``."""
    return [command for command in UV_SYNC.findall(text) if "--locked" not in command]


def test_dep10_every_workflow_installs_from_the_lock():
    """DEP-10: every uv sync in a workflow or a Dockerfile fails on a stale uv.lock."""
    sources = [
        *sorted((ROOT / ".github" / "workflows").glob("*.yml")),
        *sorted({*ROOT.glob("apps/*/Dockerfile"), *ROOT.glob("examples/*/Dockerfile")}),
    ]
    unlocked = [
        f"{path.relative_to(ROOT)}: {command}"
        for path in sources
        for command in unlocked_syncs(path.read_text())
    ]
    assert not unlocked, "DEP-10: add --locked to:\n" + "\n".join(unlocked)


def test_dep10_the_check_catches_an_unlocked_sync():
    """DEP-10: a bare uv sync is reported; one with --locked is not."""
    workflow = "      - run: uv sync --all-packages\n      - run: uv sync --locked --all-packages\n"
    assert unlocked_syncs(workflow) == ["uv sync --all-packages"]


def jobs_and_required(text: str) -> tuple[list[str], list[str]]:
    """The jobs a workflow defines, and the jobs its ``ci-passed`` job needs."""
    jobs: list[str] = []
    required: list[str] = []
    in_jobs = False
    current = ""
    for line in text.splitlines():
        if line.startswith("jobs:"):
            in_jobs = True
            continue
        if in_jobs and line and not line.startswith(" "):
            in_jobs = False
        if not in_jobs:
            continue
        if job := JOB.match(line):
            current = job.group("name")
            jobs.append(current)
        elif (needs := NEEDS.match(line)) and current == "ci-passed":
            required = [name.strip() for name in needs.group("jobs").split(",")]
    return jobs, required


def test_dep10_ci_passed_requires_every_job():
    """DEP-10: every CI job, the security gate included, is a need of ci-passed."""
    jobs, required = jobs_and_required(CI.read_text())
    assert "security" in jobs
    missing = [job for job in jobs if job != "ci-passed" and job not in required]
    assert not missing, f"DEP-10: add to ci-passed.needs: {missing}"


def test_dep10_the_check_catches_a_job_left_out_of_ci_passed():
    """DEP-10: a job missing from ci-passed's needs is reported."""
    workflow = (
        "jobs:\n"
        "  backend:\n"
        "    runs-on: ubuntu-latest\n"
        "  security:\n"
        "    runs-on: ubuntu-latest\n"
        "  ci-passed:\n"
        "    needs: [backend]\n"
    )
    jobs, required = jobs_and_required(workflow)
    assert [job for job in jobs if job != "ci-passed" and job not in required] == ["security"]
