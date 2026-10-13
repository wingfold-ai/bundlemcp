#!/usr/bin/env python3
"""Check that every requirement code is well-formed, in the right slice, unique and real.

OpenSpec identifies a requirement only by its header text and has no notion of a code, so
the conventions behind ``### Requirement: BND-5 Self-reference guard`` are enforced here:

1. Every capability folder (in ``openspec/specs/`` and in each change) is a slice listed in
   ``openspec/slices.json``, and every slice code is unique.
2. Every requirement header starts with ``<code>-<n>`` using its slice's code, followed by a
   short name.
3. No code is defined twice in the main specs. A change ADDs only codes that exist neither
   in the main specs nor in another open change; it MODIFIES, REMOVES or RENAMES only codes
   its slice's main spec has.
4. A retired code (``retired_codes`` in the registry) is never used again.
5. Every code cited in code, tests, CI, deploy files or the UI resolves to a requirement in
   the main specs or an open change. (Citations in the documentation are checked by
   ``check_docs_settings.py``.)
6. Every requirement in the main specs has a date: either in ``requirements-baseline.json``
   or from the archived change that added it.
"""

import re
import sys

from spec_ledger import (
    CHANGES,
    ROOT,
    SPECS,
    change_folders,
    deltas,
    registry,
    requirements,
    split_code,
)
from spec_ledger import (
    build as build_ledger,
)

CITATION_ROOTS = [
    "packages/bundlemcp/bundlemcp",
    "packages/bundlemcp/tests",
    "tests",
    "apps/gateway",
    "apps/web/app",
    "apps/web/tests",
    "deploy",
    ".github",
]
CITATION_SUFFIXES = {".py", ".ts", ".vue", ".mjs", ".json", ".yml", ".yaml", ".toml", ".md", ""}
IGNORED = {"node_modules", ".nuxt", ".output", "dist", "__pycache__", ".venv"}
CITATION = re.compile(r"\b([A-Z]{2,5})-([0-9]+[a-z]?)\b")


def main() -> int:
    problems: list[str] = []
    reg = registry()
    slices = {s["capability"]: s["code"] for s in reg["slices"]}
    codes = list(slices.values())
    retired = set(reg.get("retired_codes", []))
    known_prefixes = set(codes) | retired

    if dupes := sorted({c for c in codes if codes.count(c) > 1}):
        problems.append(f"slices.json: code used by more than one slice: {dupes}")
    if clash := sorted(retired & set(codes)):
        problems.append(f"slices.json: retired code reused for a slice: {clash}")

    def check_header(where: str, capability: str, prefix: str | None, code: str | None, name: str):
        expected = slices.get(capability)
        if code is None:
            problems.append(f"{where}: header does not start with a code ('<{expected}>-<n> Name')")
        elif prefix != expected:
            problems.append(
                f"{where}: {code} uses prefix {prefix}, slice {capability} is {expected}"
            )
        elif not name:
            problems.append(f"{where}: {code} has no short name after the code")

    main_ids: dict[str, str] = {}
    for spec in sorted(SPECS.glob("*/spec.md")):
        capability = spec.parent.name
        where_spec = spec.relative_to(ROOT)
        if capability not in slices:
            problems.append(f"{where_spec}: capability {capability} is not in slices.json")
            continue
        for req in requirements(spec):
            where = f"{where_spec}:{req['line']}"
            check_header(where, capability, req["prefix"], req["id"], req["name"])
            if req["id"] in main_ids:
                problems.append(f"{where}: {req['id']} already defined in {main_ids[req['id']]}")
            elif req["id"]:
                main_ids[req["id"]] = capability

    added_by: dict[str, str] = {}
    for change, archived_on, folder in change_folders():
        if archived_on is not None:
            continue  # archived deltas are history; their result is in the main specs
        for delta in sorted(folder.glob("specs/*/spec.md")):
            capability = delta.parent.name
            where_delta = delta.relative_to(ROOT)
            if capability not in slices:
                problems.append(f"{where_delta}: capability {capability} is not in slices.json")
                continue
            for op in deltas(delta):
                where = f"{where_delta}:{op['line']}"
                check_header(where, capability, op["prefix"], op["id"], op["name"])
                code = op["id"]
                if code is None:
                    continue
                if op["op"] == "ADDED":
                    if code in main_ids:
                        problems.append(f"{where}: ADDED {code} already exists in {main_ids[code]}")
                    elif code in added_by:
                        problems.append(f"{where}: {code} is also ADDED by {added_by[code]}")
                    else:
                        added_by[code] = change
                elif op["op"] == "RENAMED":
                    old = split_code(op["from"])[1]
                    if old != code:
                        problems.append(f"{where}: RENAMED changes the code {old} → {code}")
                    if code not in main_ids:
                        problems.append(f"{where}: RENAMED {code} is not in the main specs")
                elif main_ids.get(code) != capability:
                    problems.append(f"{where}: {op['op']} {code} is not in specs/{capability}")

    defined = set(main_ids) | set(added_by)
    for root in CITATION_ROOTS:
        for path in sorted((ROOT / root).rglob("*")):
            if not path.is_file() or not IGNORED.isdisjoint(path.parts):
                continue
            if path.suffix not in CITATION_SUFFIXES or path.name == "package-lock.json":
                continue
            try:
                text = path.read_text()
            except UnicodeDecodeError:
                continue
            for n, line in enumerate(text.split("\n"), 1):
                for m in CITATION.finditer(line):
                    if m.group(1) not in known_prefixes:
                        continue
                    code = f"{m.group(1)}-{m.group(2)}"
                    where = f"{path.relative_to(ROOT)}:{n}"
                    if m.group(1) in retired:
                        problems.append(f"{where}: cites {code}, a retired code")
                    elif code not in defined:
                        problems.append(f"{where}: cites {code}, which no spec or change defines")

    for entry in build_ledger()["requirements"]:
        if entry["status"] == "active" and not (
            entry["active_since"] or entry["active_since_note"]
        ):
            problems.append(
                f"{entry['id']}: active but undated — add it through an archived change "
                "(never by editing a main spec directly)"
            )

    if problems:
        sys.stderr.write("\n".join(f"  {p}" for p in problems))
        sys.stderr.write(f"\n\n{len(problems)} requirement-code problem(s).\n")
        return 1
    sys.stderr.write(
        f"{len(slices)} slices, {len(main_ids)} active and {len(added_by)} proposed requirement "
        f"codes; every header, citation and date checks out ({CHANGES.relative_to(ROOT)}/ "
        "included).\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
