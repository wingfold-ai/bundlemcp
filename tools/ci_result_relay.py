#!/usr/bin/env python3
"""Carry CI's result onto the commits CI itself pushed to a pull request's branch.

    python3 tools/ci_result_relay.py <head-sha>

CI's own commits on a branch (the changelog entry, the merge of main) say
``[skip ci]``, so no run checks them, and the branch's head would carry no
``ci-passed`` result for the required check to wait on. This walks from the head
back through CI's commits to the commit CI ran on, reads that commit's
``ci-passed`` check run, and sets the same result as a ``ci-passed`` commit
status on the head: pending while the run is going, then its outcome. A head
that is not CI's own commit has its own run, and nothing is set.

Needs ``gh`` with a token that can read checks and write statuses.
"""

import json
import os
import subprocess
import sys
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


def relayed_status(gh: Gh, repo: str, source: str) -> RelayedStatus:
    runs = json.loads(
        gh(["api", f"repos/{repo}/commits/{source}/check-runs?check_name={CONTEXT}"])
    ).get("check_runs", [])
    short = source[:7]
    if not runs:
        return RelayedStatus(
            state="pending",
            source=source,
            description=f"Waiting for CI on {short}, the commit before CI's own",
            target_url=None,
        )
    run = runs[0]
    if run["status"] != "completed":
        state, words = "pending", "running"
    else:
        state = OUTCOMES.get(run["conclusion"], "failure")
        words = "passed" if state == "success" else f"ended with {run['conclusion']}"
    return RelayedStatus(
        state=state,
        source=source,
        description=f"CI {words} on {short}, the commit before CI's own",
        target_url=run.get("html_url"),
    )


def relay(gh: Gh, repo: str, head: str) -> RelayedStatus | None:
    """Set the head's ``ci-passed`` status from the commit CI ran on; what was set, or None."""
    source = ci_source(gh, repo, head)
    if source is None:
        return None
    status = relayed_status(gh, repo, source)
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
    return status


def main() -> int:
    if len(sys.argv) != 2:
        sys.stderr.write(__doc__)
        return 2
    repo = os.environ.get("GH_REPO", "wingfold-ai/bundlemcp")
    status = relay(_gh, repo, sys.argv[1])
    if status is None:
        sys.stderr.write("The head is not CI's own commit; its own run reports the check.\n")
    else:
        sys.stderr.write(f"{CONTEXT}: {status.state} ({status.description})\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
