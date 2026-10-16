#!/usr/bin/env python3
"""Carry CI's result onto the commits CI itself pushed to a pull request's branch.

    python3 tools/ci_result_relay.py <head-sha> [--wait SECONDS]
    python3 tools/ci_result_relay.py <head-sha> --source SHA --result success|failure [--url URL]

CI's own commits on a branch (the changelog entry, the merge of main) say
``[skip ci]``, so no run checks them, and the branch's head would carry no
``ci-passed`` result for the required check to wait on. This walks from the head
back through CI's commits to the commit CI ran on and sets that commit's result
as a ``ci-passed`` commit status on the head. A head that is not CI's own commit
has its own run, and nothing is set.

Both sides of a race call it. The ``ci-passed`` job passes its own result with
``--source``, applied only when the head's CI commits sit on that very commit.
The job that pushes CI's commit reads the ``ci-passed`` check run instead: pending
while CI is still on its other jobs (the ``ci-passed`` job relays when it gets
there), and when the ``ci-passed`` job is already running, it waits up to
``--wait`` seconds for its outcome, because that job may have looked at the
branch before CI's commit arrived.

Needs ``gh`` with a token that can read checks and write statuses.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from collections.abc import Callable

from pydantic import BaseModel, Field

CONTEXT = "ci-passed"
BOT_EMAIL = "41898282+github-actions[bot]@users.noreply.github.com"
MAX_WALK = 20
OUTCOMES = {"success": "success", "skipped": "success", "neutral": "success"}


class CommitFacts(BaseModel):
    """What the walk needs to know about one commit."""

    sha: str = Field(description="The commit's full SHA")
    author_email: str = Field(description="The commit author's email")
    subject: str = Field(description="The first line of the commit message")
    first_parent: str | None = Field(description="The first parent's SHA; None for a root")

    @property
    def is_ci_commit(self) -> bool:
        return self.author_email == BOT_EMAIL and "[skip ci]" in self.subject


class RelayedStatus(BaseModel):
    """The status to set on the head, and where it came from."""

    state: str = Field(pattern=r"^(pending|success|failure)$", description="Commit status state")
    source: str = Field(description="The SHA CI ran on")
    description: str = Field(max_length=140, description="Shown beside the check on GitHub")
    target_url: str | None = Field(description="The CI run the result comes from, if known")


Gh = Callable[[list[str]], str]


def _gh(args: list[str]) -> str:
    done = subprocess.run(["gh", *args], capture_output=True, text=True, check=True)
    return done.stdout


def commit_facts(gh: Gh, repo: str, sha: str) -> CommitFacts:
    raw = json.loads(gh(["api", f"repos/{repo}/commits/{sha}"]))
    parents = raw.get("parents") or []
    return CommitFacts(
        sha=raw["sha"],
        author_email=raw["commit"]["author"]["email"],
        subject=raw["commit"]["message"].splitlines()[0],
        first_parent=parents[0]["sha"] if parents else None,
    )


def ci_source(gh: Gh, repo: str, head: str) -> str | None:
    """The commit CI ran on for ``head``, or None when ``head`` is not CI's own commit."""
    facts = commit_facts(gh, repo, head)
    if not facts.is_ci_commit:
        return None
    for _ in range(MAX_WALK):
        if facts.first_parent is None:
            return None
        facts = commit_facts(gh, repo, facts.first_parent)
        if not facts.is_ci_commit:
            return facts.sha
    return None


def _check_run(gh: Gh, repo: str, source: str) -> dict | None:
    runs = json.loads(
        gh(["api", f"repos/{repo}/commits/{source}/check-runs?check_name={CONTEXT}"])
    ).get("check_runs", [])
    return runs[0] if runs else None


def status_from_outcome(source: str, conclusion: str, url: str | None) -> RelayedStatus:
    state = OUTCOMES.get(conclusion, "failure")
    words = "passed" if state == "success" else f"ended with {conclusion}"
    return RelayedStatus(
        state=state,
        source=source,
        description=f"CI {words} on {source[:7]}, the commit before CI's own",
        target_url=url,
    )


def relayed_status(
    gh: Gh,
    repo: str,
    source: str,
    *,
    wait: float = 0,
    sleep: Callable[[float], None] = time.sleep,
) -> RelayedStatus:
    """The status ``source``'s ``ci-passed`` check run gives, waiting while it is running."""
    run = _check_run(gh, repo, source)
    waited = 0.0
    while run is not None and run["status"] == "in_progress" and waited < wait:
        sleep(10)
        waited += 10
        run = _check_run(gh, repo, source)
    if run is not None and run["status"] == "completed":
        return status_from_outcome(source, run["conclusion"], run.get("html_url"))
    running = run is not None and run["status"] == "in_progress"
    words = "CI running on" if running else "Waiting for CI on"
    return RelayedStatus(
        state="pending",
        source=source,
        description=f"{words} {source[:7]}, the commit before CI's own",
        target_url=run.get("html_url") if run else None,
    )


def post_status(gh: Gh, repo: str, head: str, status: RelayedStatus) -> None:
    args = [
        "api",
        "-X",
        "POST",
        f"repos/{repo}/statuses/{head}",
        "-f",
        f"state={status.state}",
        "-f",
        f"context={CONTEXT}",
        "-f",
        f"description={status.description}",
    ]
    if status.target_url:
        args += ["-f", f"target_url={status.target_url}"]
    gh(args)


def relay(
    gh: Gh,
    repo: str,
    head: str,
    *,
    outcome: RelayedStatus | None = None,
    wait: float = 0,
    sleep: Callable[[float], None] = time.sleep,
) -> RelayedStatus | None:
    """Set the head's ``ci-passed`` from the commit CI ran on; what was set, or None.

    With ``outcome`` (a finished run's own result) nothing is read, and nothing is
    set unless the head's CI commits sit on the commit that run checked.
    """
    source = ci_source(gh, repo, head)
    if source is None:
        return None
    if outcome is not None:
        if outcome.source != source:
            return None
        status = outcome
    else:
        status = relayed_status(gh, repo, source, wait=wait, sleep=sleep)
    post_status(gh, repo, head, status)
    if status.state == "pending":
        # The run may have finished, and set its result, between the read and the
        # pending status above; read once more so pending never has the last word.
        again = relayed_status(gh, repo, source)
        if again.state != "pending":
            post_status(gh, repo, head, again)
            status = again
    return status


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("head", help="The branch head to set the status on")
    parser.add_argument("--wait", type=float, default=0, help="Seconds to wait for a running check")
    parser.add_argument("--source", help="The commit a finished run checked")
    parser.add_argument("--result", help="That run's conclusion, e.g. success or failure")
    parser.add_argument("--url", help="That run's page")
    args = parser.parse_args()
    if (args.source is None) != (args.result is None):
        parser.error("--source and --result go together")
    repo = os.environ.get("GH_REPO", "wingfold-ai/bundlemcp")
    outcome = status_from_outcome(args.source, args.result, args.url) if args.source else None
    status = relay(_gh, repo, args.head, outcome=outcome, wait=args.wait)
    if status is None:
        sys.stderr.write("Nothing to set: the head has its own run, or sits on another commit.\n")
    else:
        sys.stderr.write(f"{CONTEXT}: {status.state} ({status.description})\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
