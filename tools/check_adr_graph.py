#!/usr/bin/env python3
"""Check (or regenerate) the ADR amendment graph and the two indexes built from it.

Three invariants, all from DOC-8 (the documentation spec):

1. Every ``**Amends:** NNNN`` has a matching ``**Amended by:**`` (or
   ``superseded by``) on each ADR it names, so a reader who lands on the older
   record learns it was revised.
2. ``docs/adr/README.md``'s Status column agrees with each file's status line.
3. ``docs/arc42/09-architecture-decisions.md`` lists every ADR with the same
   status.

Run with ``--fix`` to rewrite the two index tables from the files. The status
lines themselves are never rewritten: choosing between "amended" and
"superseded" is an editorial decision, so a missing back-pointer is reported.
"""

import argparse
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
ADR_DIR = ROOT / "docs" / "adr"
ADR_INDEX = ADR_DIR / "README.md"
ARC42_INDEX = ROOT / "docs" / "arc42" / "09-architecture-decisions.md"

ROW = re.compile(r"^\| \[(\d{4})\]\(([^)]+)\) \|(?P<cells>.*)\|$")


def referenced(line: str, label: str) -> list[str]:
    """The ADR numbers a labelled segment of a status line names."""
    if f"**{label}:**" in line:
        segment = line.split(f"**{label}:**", 1)[1]
        for later in ("**Amends:**", "**Amended by:**", "**Superseded by:**"):
            segment = segment.split(later)[0]
        return re.findall(r"ADR-(\d{4})", segment)
    if label == "Superseded by" and "superseded by" in line:
        tail = line.split("superseded by", 1)[1].split("·")[0]
        return re.findall(r"ADR-(\d{4})", tail)
    return []


def status_paragraph(path: pathlib.Path) -> str:
    """The record's status paragraph as one line; Markdown wrapping may split it."""
    paragraph = path.read_text().split("\n\n")[1]
    return " ".join(paragraph.split())


def status_cell(line: str) -> str:
    """The status line as one index cell: the state, plus who amended it."""
    state = line.split("**Status:**", 1)[1].split("·")[0]
    state = re.sub(r"\[ADR-(\d{4})\]\([^)]+\)", r"\1", state).strip()
    amenders = referenced(line, "Amended by")
    return f"{state} (amended by {', '.join(amenders)})" if amenders else state


def check_graph(lines: dict[str, str], known: set[str]) -> list[str]:
    problems = []
    for num, line in lines.items():
        for target in referenced(line, "Amends"):
            if target not in known:
                problems.append(f"ADR-{num} amends ADR-{target}, which does not exist")
                continue
            back = referenced(lines[target], "Amended by") + referenced(
                lines[target], "Superseded by"
            )
            if num not in back:
                problems.append(
                    f"ADR-{target} is amended by ADR-{num} but records neither "
                    f"'Amended by: ADR-{num}' nor 'superseded by ADR-{num}'"
                )
        for target in referenced(line, "Amended by") + referenced(line, "Superseded by"):
            if target in known and num not in referenced(lines[target], "Amends"):
                problems.append(
                    f"ADR-{num} says ADR-{target} amends it, but ADR-{target} "
                    f"has no 'Amends: ADR-{num}'"
                )
    return problems


def check_index(
    index: pathlib.Path, status_column: int, lines: dict[str, str], *, fix: bool
) -> list[str]:
    """Verify (and optionally rewrite) one index table's status column."""
    problems: list[str] = []
    out: list[str] = []
    seen: set[str] = set()
    for line in index.read_text().split("\n"):
        match = ROW.match(line)
        if not match:
            out.append(line)
            continue
        num, href = match.group(1), match.group(2)
        cells = [c.strip() for c in match.group("cells").split(" | ")]
        seen.add(num)
        if num not in lines:
            problems.append(f"{index.name} lists ADR-{num}, which does not exist")
            out.append(line)
            continue
        want = status_cell(lines[num])
        if len(cells) <= status_column:
            problems.append(f"{index.name} row for ADR-{num} has no status column")
            out.append(line)
            continue
        if cells[status_column] != want:
            problems.append(
                f"{index.name} row for ADR-{num} says {cells[status_column]!r}, "
                f"the record says {want!r}"
            )
            cells[status_column] = want
        out.append(f"| [{num}]({href}) | " + " | ".join(cells) + " |")
    problems.extend(f"{index.name} does not list ADR-{num}" for num in sorted(set(lines) - seen))
    if fix:
        index.write_text("\n".join(out))
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fix", action="store_true", help="rewrite the two index tables")
    args = parser.parse_args()

    files = {p.name[:4]: p for p in sorted(ADR_DIR.glob("0*.md"))}
    lines = {num: status_paragraph(path) for num, path in files.items()}

    problems = check_graph(lines, set(files))
    problems += check_index(ADR_INDEX, 1, lines, fix=args.fix)
    problems += check_index(ARC42_INDEX, 1, lines, fix=args.fix)

    if problems:
        sys.stderr.write("\n".join(f"  {p}" for p in problems))
        sys.stderr.write(f"\n\n{len(problems)} ADR index/graph problem(s).\n")
        if not args.fix:
            sys.stderr.write(
                "Run 'python3 tools/check_adr_graph.py --fix' to rewrite the tables.\n"
            )
        return 1
    sys.stderr.write(f"ADR graph and indexes consistent across {len(files)} records.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
