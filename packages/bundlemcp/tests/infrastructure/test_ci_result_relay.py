"""CI's result carried onto the commits CI pushed to a branch, for the required check (DEP-12)."""

import importlib.util
import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[4]
_spec = importlib.util.spec_from_file_location("ci_result_relay", ROOT / "tools/ci_result_relay.py")
assert _spec is not None and _spec.loader is not None
relay = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(relay)

REPO = "wingfold-ai/bundlemcp"
AUTHOR = "someone@example.com"


class FakeGh:
    """Commits and check runs as the GitHub API returns them, and the statuses set."""

    def __init__(self, commits, runs):
        self.commits = commits
        self.runs = runs
        self.posted: list[dict[str, str]] = []

    def __call__(self, args):
        path = args[-1] if args[1] != "-X" else args[3]
        if args[1] == "-X":
            fields = dict(arg.split("=", 1) for arg in args[4:] if arg != "-f")
            self.posted.append({"path": path, **fields})
            return "{}"
        if "/check-runs" in path:
            sha = path.split("/commits/")[1].split("/")[0]
            runs = self.runs.get(sha, [])
            if callable(runs):
                runs = runs()
            return json.dumps({"check_runs": runs})
        sha = path.rsplit("/", 1)[1]
        email, subject, parent = self.commits[sha]
        return json.dumps(
            {
                "sha": sha,
                "commit": {"author": {"email": email}, "message": f"{subject}\n\nbody"},
                "parents": [{"sha": parent}] if parent else [],
            }
        )


def _history():
    return {
        "a1": (AUTHOR, "feat(x): Y", None),
        "m2": (relay.BOT_EMAIL, "chore(repo): Merge origin/main [skip ci]", "a1"),
        "r3": (relay.BOT_EMAIL, "chore(repo): Release 1.2.0 [skip ci]", "m2"),
    }


@pytest.mark.parametrize(
    ("runs", "state", "words"),
    [
        ({}, "pending", "Waiting for CI on a1"),
        ({"a1": [{"status": "in_progress", "conclusion": None}]}, "pending", "CI running on a1"),
        ({"a1": [{"status": "completed", "conclusion": "success"}]}, "success", "CI passed"),
        ({"a1": [{"status": "completed", "conclusion": "failure"}]}, "failure", "ended with"),
        ({"a1": [{"status": "completed", "conclusion": "cancelled"}]}, "failure", "cancelled"),
    ],
)
def test_dep12_ci_commit_head_carries_the_result_of_the_commit_ci_ran_on(runs, state, words):
    gh = FakeGh(_history(), runs)
    status = relay.relay(gh, REPO, "r3")
    assert status is not None and status.source == "a1"
    (posted,) = gh.posted
    assert posted["path"] == f"repos/{REPO}/statuses/r3"
    assert posted["context"] == "ci-passed" and posted["state"] == state
    assert words in posted["description"]


def test_dep12_an_author_head_is_left_to_its_own_run():
    gh = FakeGh(_history(), {})
    assert relay.relay(gh, REPO, "a1") is None
    assert gh.posted == []


def test_dep12_a_bot_commit_without_skip_ci_is_not_relayed():
    commits = {**_history(), "b4": (relay.BOT_EMAIL, "chore(repo): Something", "r3")}
    gh = FakeGh(commits, {})
    assert relay.relay(gh, REPO, "b4") is None


def test_dep12_the_ci_passed_job_sets_its_own_result_on_ci_s_commit():
    gh = FakeGh(_history(), {})
    outcome = relay.status_from_outcome("a1", "success", "https://run")
    status = relay.relay(gh, REPO, "r3", outcome=outcome)
    assert status is not None and status.state == "success"
    assert gh.posted[0]["target_url"] == "https://run"


def test_dep12_a_result_for_another_commit_is_not_set():
    gh = FakeGh(_history(), {})
    outcome = relay.status_from_outcome("older", "failure", None)
    assert relay.relay(gh, REPO, "r3", outcome=outcome) is None
    assert gh.posted == []


def test_dep12_a_running_ci_passed_job_is_waited_for():
    states = iter(["in_progress", "in_progress", "completed"])

    def runs():
        state = next(states)
        return [{"status": state, "conclusion": "success" if state == "completed" else None}]

    gh = FakeGh(_history(), {"a1": runs})
    status = relay.relay(gh, REPO, "r3", wait=60, sleep=lambda seconds: None)
    assert status is not None and status.state == "success"
    assert [post["state"] for post in gh.posted] == ["success"]


def test_dep12_a_result_arriving_after_the_pending_status_replaces_it():
    states = iter(["queued", "completed"])

    def runs():
        state = next(states)
        return [{"status": state, "conclusion": "success" if state == "completed" else None}]

    gh = FakeGh(_history(), {"a1": runs})
    status = relay.relay(gh, REPO, "r3")
    assert status is not None and status.state == "success"
    assert [post["state"] for post in gh.posted] == ["pending", "success"]


def test_dep12_a_pending_status_links_to_the_running_ci():
    gh = FakeGh(_history(), {})
    relay.relay(gh, REPO, "r3")
    assert gh.posted[0]["target_url"] == f"https://github.com/{REPO}/commit/a1/checks"
