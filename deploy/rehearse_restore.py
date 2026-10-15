"""Rehearse the documented restore against the running compose stack.

Mints an API key on the running gateway, dumps its database, restores the dump
into a scratch database, starts a second gateway on that database with the same
encryption keys (bootstrap and the initial service key switched off), waits for
/readyz and makes one tool call with the minted key. That key exists only in
the dump, so the call succeeding proves the restore carried the data over.

    uv run python deploy/rehearse_restore.py            # the rehearsal
    uv run python deploy/rehearse_restore.py --skip-restore   # must fail

Needs the compose stack up (``docker compose -f deploy/docker-compose.yml up
-d --wait``) with the demo seed discovered. Exits non-zero on any failed step.
"""

import argparse
import os
import pathlib
import subprocess
import sys
import tempfile
import time

import httpx

COMPOSE = ["docker", "compose", "-f", "deploy/docker-compose.yml"]
GATEWAY = os.environ.get("BUNDLEMCP_GATEWAY_URL", "http://localhost:8000")
SERVICE_KEY = os.environ.get(
    "BUNDLEMCP_INITIAL_SERVICE_KEY", "bmcp_sk_devservicekey000000000000000000000000"
)
SCRATCH_DB = "bundlemcp_restore_rehearsal"
CONTAINER = "bundlemcp-restore-rehearsal"
RESTORED_PORT = 8001
RESTORED = f"http://localhost:{RESTORED_PORT}"


def step(message: str) -> None:
    sys.stderr.write(f"==> {message}\n")


def psql(*args: str, stdin=None, db: str = "postgres") -> None:
    subprocess.run(
        [*COMPOSE, "exec", "-T", "postgres", "psql", "-v", "ON_ERROR_STOP=1", "-q"]
        + ["-U", "bundlemcp", "-d", db, *args],
        check=True,
        stdin=stdin,
        stdout=subprocess.DEVNULL,
    )


def wait_ready(base_url: str, timeout: float = 180.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"{base_url}/readyz", timeout=5).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(2)
    raise SystemExit(f"{base_url}/readyz did not answer 200 within {timeout:.0f}s")


def mint_key() -> str:
    """An endpoint key that exists only in the original database."""
    resp = httpx.post(
        f"{GATEWAY}/api/v1/api-keys",
        headers={"Authorization": f"Bearer {SERVICE_KEY}"},
        json={"name": f"restore-rehearsal-{int(time.time())}", "kind": "endpoint"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["key"]


def dump(path: pathlib.Path) -> None:
    with path.open("wb") as out:
        subprocess.run(
            [*COMPOSE, "exec", "-T", "postgres", "pg_dump", "-U", "bundlemcp", "bundlemcp"],
            check=True,
            stdout=out,
        )


def restore(path: pathlib.Path, *, skip: bool) -> None:
    psql("-c", f"DROP DATABASE IF EXISTS {SCRATCH_DB}")
    psql("-c", f"CREATE DATABASE {SCRATCH_DB}")
    if skip:
        return
    with path.open("rb") as dumped:
        psql(stdin=dumped, db=SCRATCH_DB)


def start_restored_gateway() -> None:
    subprocess.run(["docker", "rm", "-f", CONTAINER], capture_output=True)
    subprocess.run(
        [*COMPOSE, "run", "-d", "--no-deps", "--name", CONTAINER]
        + ["-p", f"{RESTORED_PORT}:8000"]
        + [
            "-e",
            f"BUNDLEMCP_DATABASE_URL=postgresql+asyncpg://bundlemcp:bundlemcp@postgres:5432/"
            f"{SCRATCH_DB}",
            # nothing may recreate what the dump should have carried
            "-e",
            "BUNDLEMCP_BOOTSTRAP_FILE=",
            "-e",
            "BUNDLEMCP_INITIAL_SERVICE_KEY=",
            "gateway",
        ],
        check=True,
        stdout=subprocess.DEVNULL,
    )


def tool_call(base_url: str, key: str) -> str:
    """Initialize on the demo endpoint and call its echo tool; returns the echoed text."""
    headers = {"Authorization": f"Bearer {key}"}
    with httpx.Client(base_url=base_url, headers=headers, timeout=30) as mcp:
        init = mcp.post(
            "/demo/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-11-25", "capabilities": {}},
            },
        )
        if init.status_code != 200:
            raise SystemExit(f"initialize on the restored gateway answered {init.status_code}")
        call = mcp.post(
            "/demo/mcp",
            headers={"Mcp-Session-Id": init.headers["mcp-session-id"]},
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "echo__echo", "arguments": {"text": "restored"}},
            },
        )
    body = call.json()
    if "result" not in body:
        raise SystemExit(f"the tool call on the restored gateway failed: {body.get('error')}")
    return body["result"]["content"][0]["text"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--skip-restore",
        action="store_true",
        help="Leave the scratch database empty, to check the rehearsal fails without a restore",
    )
    parser.add_argument(
        "--keep", action="store_true", help="Leave the restored gateway and database running"
    )
    args = parser.parse_args()

    wait_ready(GATEWAY)
    step("minting an endpoint key on the running gateway")
    key = mint_key()
    with tempfile.TemporaryDirectory() as scratch:
        path = pathlib.Path(scratch) / "bundlemcp.sql"
        step("dumping the database")
        dump(path)
        step("restoring into a scratch database" + (" (skipped)" if args.skip_restore else ""))
        restore(path, skip=args.skip_restore)
    try:
        step("starting a gateway on the restored database with the same encryption keys")
        start_restored_gateway()
        wait_ready(RESTORED)
        step("making one tool call with the key from the dump")
        echoed = tool_call(RESTORED, key)
        if echoed != "restored":
            raise SystemExit(f"the restored gateway echoed {echoed!r}")
        step("restore rehearsal passed")
        return 0
    finally:
        if not args.keep:
            subprocess.run(["docker", "rm", "-f", CONTAINER], capture_output=True)
            psql("-c", f"DROP DATABASE IF EXISTS {SCRATCH_DB} WITH (FORCE)")


if __name__ == "__main__":
    sys.exit(main())
