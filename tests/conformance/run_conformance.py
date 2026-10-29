"""Run the MCP conformance suite against the gateway on the compose stack.

The suite checks a server through fixed fixtures (tools, resources and prompts
with fixed names). ``examples/conformance-mcp`` serves them as an upstream; this
harness bundles it behind an open ``conformance`` endpoint, presents each tool
under its upstream name and adds the two plain prompts as the bundle's own (a
member's prompts are always served under its prefix), then runs the suite for
one protocol revision through the gateway. ``baseline.yml`` lists the scenarios
the gateway fails by design, each with the reason.

    docker compose -f deploy/docker-compose.yml --profile conformance up -d --build --wait
    uv run python tests/conformance/run_conformance.py --revision 2025-11-25
    uv run python tests/conformance/run_conformance.py --list-revisions   # JSON, for a CI matrix

Exits with the suite's status: non-zero on a failure the baseline does not list,
or on a baseline entry that now passes.
"""

import argparse
import json
import os
import pathlib
import subprocess
import sys
import time

import httpx
from bundlemcp.api.mcp.protocol.dialect import DialectRegistry

SUITE = "@modelcontextprotocol/conformance@0.1.16"
GATEWAY = os.environ.get("BUNDLEMCP_GATEWAY_URL", "http://localhost:8000")
SERVICE_KEY = os.environ.get(
    "BUNDLEMCP_INITIAL_SERVICE_KEY", "bmcp_sk_devservicekey000000000000000000000000"
)
UPSTREAM = "conformance"
UPSTREAM_URL = "http://conformance-mcp:9000/mcp"
BUNDLE = ENDPOINT = "conformance"
HERE = pathlib.Path(__file__).resolve().parent
BASELINE = HERE / "baseline.yml"

# The two prompts the suite gets by name; a bundle's own prompts keep it.
BUNDLE_PROMPTS = [
    {
        "name": "test_simple_prompt",
        "description": "A simple prompt without arguments",
        "arguments": [],
        "messages": [{"role": "user", "text": "This is a simple prompt for testing."}],
    },
    {
        "name": "test_prompt_with_arguments",
        "description": "A prompt with two required arguments",
        "arguments": [
            {
                "name": "arg1",
                "description": "First test argument",
                "required": True,
                "values": ["paris", "park", "party"],
            },
            {"name": "arg2", "description": "Second test argument", "required": True},
        ],
        "messages": [
            {
                "role": "user",
                "text": "Prompt with arguments: arg1='{{arg1}}', arg2='{{arg2}}'",
            }
        ],
    },
]


def step(message: str) -> None:
    sys.stderr.write(f"==> {message}\n")


def served_revisions() -> list[str]:
    """Every protocol revision the gateway serves, newest first."""
    dialects = DialectRegistry.default(legacy_enabled=True)
    return [*dialects.modern_versions, *dialects.handshake_versions]


def suite_covers(revision: str) -> bool:
    """Whether the suite has any server scenario for ``revision``."""
    listing = subprocess.run(
        ["npx", "--yes", SUITE, "list", "--server", "--spec-version", revision],
        capture_output=True,
        text=True,
    )
    # a revision the suite does not know yet is refused with a non-zero exit
    if listing.returncode != 0:
        return False
    return any(line.strip().startswith("- ") for line in listing.stdout.splitlines())


def wait_ready(timeout: float = 180.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"{GATEWAY}/readyz", timeout=5).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(2)
    raise SystemExit(f"{GATEWAY}/readyz did not answer 200 within {timeout:.0f}s")


def configure() -> None:
    """The fixture upstream, its bundle and the open endpoint the suite connects to."""
    with httpx.Client(
        base_url=f"{GATEWAY}/api/v1",
        headers={"Authorization": f"Bearer {SERVICE_KEY}"},
        timeout=60,
    ) as api:
        # the fixture asks for sampling and elicitation with server-initiated requests,
        # which only the handshake era carries
        api.put(
            f"/upstreams/{UPSTREAM}",
            json={"name": UPSTREAM, "url": UPSTREAM_URL, "protocol_mode": "session"},
        ).raise_for_status()
        discovered = 0
        for _ in range(30):
            refresh = api.post(f"/upstreams/{UPSTREAM}:refresh-tools")
            discovered = refresh.json().get("discovered", 0) if refresh.is_success else 0
            if discovered:
                break
            time.sleep(2)
        if not discovered:
            raise SystemExit("the conformance fixture server listed no tools")
        api.put(f"/bundles/{BUNDLE}", json={"name": BUNDLE}).raise_for_status()
        api.put(
            f"/bundles/{BUNDLE}/upstreams/{UPSTREAM}", json={"enabled": True}
        ).raise_for_status()
        # the suite calls each tool by its own name, not the gateway's prefixed one
        for tool in api.get(f"/bundles/{BUNDLE}/tools").json():
            api.put(
                f"/bundles/{BUNDLE}/tools/{tool['tool_id']}",
                json={"enabled": True, "override_name": tool["name"]},
            ).raise_for_status()
        for prompt in BUNDLE_PROMPTS:
            api.put(f"/bundles/{BUNDLE}/prompts/{prompt['name']}", json=prompt).raise_for_status()
        api.put(
            f"/endpoints/{ENDPOINT}",
            json={
                "name": ENDPOINT,
                "bundle_name": BUNDLE,
                "auth_modes": ["none"],
                "allow_unauthenticated": True,
            },
        ).raise_for_status()


def run_suite(revision: str, output: pathlib.Path | None) -> int:
    command = ["npx", "--yes", SUITE, "server", "--url", f"{GATEWAY}/{ENDPOINT}/mcp"]
    command += ["--spec-version", revision, "--expected-failures", str(BASELINE)]
    if output is not None:
        command += ["--output-dir", str(output)]
    return subprocess.run(command).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--revision", help="Protocol revision to run the suite for")
    parser.add_argument(
        "--list-revisions",
        action="store_true",
        help="Print the served revisions the suite has scenarios for, as JSON",
    )
    parser.add_argument("--output-dir", type=pathlib.Path, help="Where the suite saves results")
    args = parser.parse_args()

    if args.list_revisions:
        sys.stdout.write(json.dumps([r for r in served_revisions() if suite_covers(r)]) + "\n")
        return 0
    if args.revision not in served_revisions():
        parser.error(f"--revision must be one of {', '.join(served_revisions())}")
    wait_ready()
    step("configuring the conformance bundle and endpoint")
    configure()
    step(f"running {SUITE} for {args.revision}")
    return run_suite(args.revision, args.output_dir)


if __name__ == "__main__":
    sys.exit(main())
