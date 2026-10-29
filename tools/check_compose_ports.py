#!/usr/bin/env python3
"""Check that every host port the development compose files publish is bound to loopback.

The development stack carries well-known credentials, so nothing it publishes may
listen on an interface other hosts can reach: a `ports:` entry must name
`127.0.0.1` (or `[::1]`) as its host address. A tunnel or proxy reaches the
services over the compose network and needs no host port.

Usage: python3 tools/check_compose_ports.py [compose-file ...]
With no arguments it checks deploy/docker-compose*.yml.
"""

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
LOOPBACK = ("127.0.0.1:", "[::1]:")
PORTS_KEY = re.compile(r"^(?P<indent>\s*)ports:")
ITEM = re.compile(r"^(?P<indent>\s*)-\s*(?P<value>.+?)\s*(#.*)?$")


def unbound_ports(text: str) -> list[tuple[int, str]]:
    """``(line, entry)`` for each `ports:` list entry that does not bind to loopback."""
    found: list[tuple[int, str]] = []
    ports_indent: int | None = None
    for number, line in enumerate(text.splitlines(), start=1):
        key = PORTS_KEY.match(line)
        if key:
            ports_indent = len(key.group("indent"))
            continue
        if ports_indent is None or not line.strip():
            continue
        item = ITEM.match(line)
        if item is None or len(item.group("indent")) <= ports_indent:
            ports_indent = None
            continue
        entry = item.group("value").strip("'\"")
        if not entry.startswith(LOOPBACK):
            found.append((number, entry))
    return found


def main(argv: list[str]) -> int:
    files = [pathlib.Path(a) for a in argv] or sorted((ROOT / "deploy").glob("docker-compose*.yml"))
    failures = [
        f"{path}:{number}: host port {entry!r} is not bound to 127.0.0.1 (DEP-13)"
        for path in files
        for number, entry in unbound_ports(path.read_text())
    ]
    if failures:
        sys.stderr.write("\n".join(failures) + "\n")
        return 1
    sys.stderr.write(
        f"Every published host port is loopback-bound across {len(files)} compose files.\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
