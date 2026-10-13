#!/usr/bin/env python3
"""Build the requirements ledger: every requirement code, its slice, status and dates.

Sources, all inside ``openspec/``:

* ``slices.json`` — the registry of slices (OpenSpec capabilities) and their code prefixes;
* ``specs/<capability>/spec.md`` — what is implemented today;
* ``changes/<change>/specs/<capability>/spec.md`` — open changes, not yet implemented;
* ``changes/archive/<YYYY-MM-DD>-<change>/specs/...`` — implemented changes, dated by
  their folder;
* ``requirements-baseline.json`` — frozen dates for the requirements that predate OpenSpec.

Nothing here is written by hand except the registry: archiving a change is what dates a
requirement. The docs site's requirements page and ``tools/check_spec_ids.py`` both read it.

Usage: ``python3 tools/spec_ledger.py`` prints the ledger as JSON.
"""

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
OPENSPEC = ROOT / "openspec"
SPECS = OPENSPEC / "specs"
CHANGES = OPENSPEC / "changes"
ARCHIVE = CHANGES / "archive"
REPO_URL = "https://github.com/wingfold-ai/bundlemcp/blob/main"

HEADER = re.compile(r"^### Requirement: (.+?)\s*$")
CODE = re.compile(r"^([A-Z]{2,5})-([0-9]+[a-z]?)(?: (.*))?$")
SECTION = re.compile(r"^## (ADDED|MODIFIED|REMOVED|RENAMED) Requirements\s*$")
RENAME = re.compile(r"^- (FROM|TO): `### Requirement: (.+?)`\s*$")
ARCHIVED = re.compile(r"^(\d{4}-\d{2}-\d{2})-(.+)$")


def registry() -> dict:
    return json.loads((OPENSPEC / "slices.json").read_text())


def baseline() -> dict:
    return json.loads((OPENSPEC / "requirements-baseline.json").read_text())


def split_code(header: str) -> tuple[str | None, str | None, str]:
    """``"BND-5 Self-reference guard"`` → ``("BND", "BND-5", "Self-reference guard")``."""
    m = CODE.match(header)
    if not m:
        return None, None, header
    return m.group(1), f"{m.group(1)}-{m.group(2)}", m.group(3) or ""


def requirements(path: pathlib.Path) -> list[dict]:
    """The requirements a main spec defines, in file order, with their first paragraph."""
    found: list[dict] = []
    lines = path.read_text().split("\n")
    for i, line in enumerate(lines):
        m = HEADER.match(line)
        if not m:
            continue
        prefix, code, name = split_code(m.group(1))
        text = first_paragraphs(lines, i)
        full = block(lines, i, path)
        found.append(
            {
                "header": m.group(1),
                "prefix": prefix,
                "id": code,
                "name": name,
                "text": text,
                "md": full["md"],
                "scenarios": full["scenarios"],
                "line": i + 1,
            }
        )
    return found


def first_paragraphs(lines: list[str], header_index: int) -> str:
    """The requirement text: everything between its header and the first scenario, on one line."""
    body: list[str] = []
    for following in lines[header_index + 1 :]:
        if following.startswith("#"):
            break
        body.append(following.strip())
    return " ".join(" ".join(body).split())


def block(lines: list[str], header_index: int, source: pathlib.Path) -> dict:
    """A requirement's Markdown body and its scenarios, with relative links made absolute.

    The body is everything up to the first ``#### Scenario:``; each scenario runs to the next
    scenario or requirement. Links are rewritten against the repository on GitHub, so the
    Markdown renders correctly outside ``openspec/``.
    """
    body: list[str] = []
    scenarios: list[dict] = []
    for following in lines[header_index + 1 :]:
        if following.startswith(("### ", "## ", "# ")):
            break
        if following.startswith("#### Scenario:"):
            scenarios.append({"name": following.split(":", 1)[1].strip(), "md": []})
            continue
        (scenarios[-1]["md"] if scenarios else body).append(following)
    rel = source.relative_to(ROOT).parts
    if "changes" in rel and rel[-3] == "specs":
        # a delta spec links as the main spec it will be merged into
        folder = f"openspec/specs/{rel[-2]}"
    else:
        folder = source.parent.relative_to(ROOT).as_posix()

    def absolute(text: str) -> str:
        def link(m: re.Match) -> str:
            target = m.group(2)
            if re.match(r"^[a-z]+:|^#", target):
                return m.group(0)
            resolved = pathlib.PurePosixPath(folder, target).as_posix()
            parts: list[str] = []
            for part in resolved.split("/"):
                if part == "..":
                    if not parts:
                        return m.group(0)  # climbs out of the repository: leave it as written
                    parts.pop()
                elif part != ".":
                    parts.append(part)
            return f"[{m.group(1)}]({REPO_URL}/{'/'.join(parts)})"

        return re.sub(r"\[([^\]]*)\]\(([^)\s]+)\)", link, "\n".join(text).strip())

    return {
        "md": absolute(body),
        "scenarios": [{"name": sc["name"], "md": absolute(sc["md"])} for sc in scenarios],
    }


def deltas(path: pathlib.Path) -> list[dict]:
    """The operations a delta spec carries: ADDED/MODIFIED/REMOVED headers and RENAMED pairs."""
    ops: list[dict] = []
    section = None
    rename_from = None
    lines = path.read_text().split("\n")
    for i, line in enumerate(lines):
        if s := SECTION.match(line):
            section = s.group(1)
            continue
        if line.startswith("## "):
            section = None
            continue
        if section == "RENAMED" and (r := RENAME.match(line)):
            if r.group(1) == "FROM":
                rename_from = r.group(2)
            elif rename_from is not None:
                prefix, code, name = split_code(r.group(2))
                ops.append(
                    {
                        "op": "RENAMED",
                        "header": r.group(2),
                        "from": rename_from,
                        "prefix": prefix,
                        "id": code,
                        "name": name,
                        "line": i + 1,
                    }
                )
                rename_from = None
            continue
        if section in {"ADDED", "MODIFIED", "REMOVED"} and (m := HEADER.match(line)):
            prefix, code, name = split_code(m.group(1))
            ops.append(
                {
                    "op": section,
                    "header": m.group(1),
                    "prefix": prefix,
                    "id": code,
                    "name": name,
                    "text": first_paragraphs(lines, i),
                    **{k: v for k, v in block(lines, i, path).items()},
                    "line": i + 1,
                }
            )
    return ops


def change_folders() -> list[tuple[str, str | None, pathlib.Path]]:
    """``(change, archive date or None, folder)`` for every open and archived change."""
    folders: list[tuple[str, str | None, pathlib.Path]] = []
    for folder in sorted(CHANGES.iterdir()):
        if folder.is_dir() and folder.name != "archive":
            folders.append((folder.name, None, folder))
    if ARCHIVE.exists():
        for folder in sorted(ARCHIVE.iterdir()):
            if folder.is_dir() and (m := ARCHIVED.match(folder.name)):
                folders.append((m.group(2), m.group(1), folder))
    return folders


def change_created(folder: pathlib.Path) -> str | None:
    meta = folder / ".openspec.yaml"
    if meta.exists():
        for line in meta.read_text().split("\n"):
            if line.startswith("created:"):
                return line.split(":", 1)[1].strip().strip("'\"") or None
    return None


def former_codes() -> dict[str, list[str]]:
    """Each current code → the codes it was published under before the slices were merged."""
    former: dict[str, list[str]] = {}
    for old, new in registry().get("former_codes", {}).items():
        if not old.startswith("$"):
            former.setdefault(new, []).append(old)
    return former


def build() -> dict:
    slices = registry()["slices"]
    by_capability = {s["capability"]: s for s in slices}
    former = former_codes()
    base = baseline()
    ledger: dict[str, dict] = {}

    def entry(code: str, capability: str) -> dict:
        slice_ = by_capability.get(capability, {})
        return ledger.setdefault(
            code,
            {
                "id": code,
                "capability": capability,
                "code": slice_.get("code"),
                "group": slice_.get("group"),
                "slice_title": slice_.get("title"),
                "former_ids": former.get(code, []),
                "name": "",
                "text": "",
                "md": "",
                "scenarios": [],
                "status": "proposed",
                "specified": None,
                "active_since": None,
                "active_since_note": None,
                "last_changed": None,
                "open_changes": [],
                "history": [],
                "url": None,
            },
        )

    for spec in sorted(SPECS.glob("*/spec.md")):
        capability = spec.parent.name
        for req in requirements(spec):
            if not req["id"]:
                continue
            e = entry(req["id"], capability)
            e.update(
                name=req["name"],
                text=req["text"],
                md=req["md"],
                scenarios=req["scenarios"],
                status="active",
            )
            anchor = re.sub(r"[^\w\s-]", "", f"requirement: {req['header']}".lower()).replace(
                " ", "-"
            )
            e["url"] = f"{REPO_URL}/openspec/specs/{capability}/spec.md#{anchor}"
            if dates := base["requirements"].get(req["id"]):
                e["specified"] = dates["specified"]
                e["active_since"] = dates["implemented"]
                if dates["implemented"] is None:
                    e["active_since_note"] = f"on or before {base['migrated_on']}"

    for change, archived_on, folder in change_folders():
        for delta in sorted(folder.glob("specs/*/spec.md")):
            capability = delta.parent.name
            for op in deltas(delta):
                if not op["id"]:
                    continue
                e = entry(op["id"], capability)
                event = {
                    "op": op["op"],
                    "change": change,
                    "date": archived_on or change_created(folder),
                    "archived": archived_on is not None,
                }
                e["history"].append(event)
                if archived_on is None:
                    e["open_changes"].append({"change": change, "op": op["op"]})
                    if e["status"] == "proposed" and op["op"] == "ADDED":
                        e["name"] = e["name"] or op["name"]
                        e["text"] = e["text"] or op["text"]
                        e["md"] = e["md"] or op["md"]
                        e["scenarios"] = e["scenarios"] or op["scenarios"]
                        dates = base["requirements"].get(op["id"], {})
                        e["specified"] = dates.get("specified") or event["date"]
                        e["url"] = f"{REPO_URL}/openspec/changes/{change}/proposal.md"
                    continue
                if op["op"] == "ADDED":
                    e["active_since"] = archived_on
                    e["specified"] = e["specified"] or change_created(folder)
                elif op["op"] in {"MODIFIED", "RENAMED"}:
                    e["last_changed"] = max(filter(None, [e["last_changed"], archived_on]))
                elif op["op"] == "REMOVED" and e["status"] != "active":
                    e["status"] = "retired"

    for e in ledger.values():
        e["history"].sort(key=lambda h: (h["date"] or "", h["change"]))
    return {
        "slices": slices,
        "retired_codes": registry().get("retired_codes", []),
        "former_codes": {
            k: v for k, v in registry().get("former_codes", {}).items() if k[0] != "$"
        },
        "migrated_on": base["migrated_on"],
        "requirements": sorted(ledger.values(), key=lambda e: sort_key(e["id"])),
    }


def sort_key(code: str) -> tuple:
    prefix, number = code.split("-", 1)
    m = re.match(r"(\d+)(.*)", number)
    return (prefix, int(m.group(1)), m.group(2)) if m else (prefix, 0, number)


if __name__ == "__main__":
    json.dump(build(), sys.stdout, indent=2)
    sys.stdout.write("\n")
