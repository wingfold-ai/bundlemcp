#!/usr/bin/env python3
"""Check that documented settings and requirement IDs correspond to real ones.

Three checks, all currently green, kept green cheaply:

1. Every ``BUNDLEMCP_*`` variable the documentation mentions is a real ``Settings``
   field, **and** every field is documented. The second direction is the one that
   rots silently: a new setting nobody documents is invisible to operators.
2. Every requirement ID the documentation cites (``SRV-1``, ``EP-3``, …) resolves
   to something in ``spec/``.
3. No requirement ID appears in a docstring or a Pydantic ``description``. The
   convention is that IDs belong in ``#`` comments, test names and error
   messages, because docstrings and descriptions are read by people — and, for
   ``schemas/`` and ``Settings``, published to API consumers — who cannot look an
   ID up. Alembic revision docstrings are exempt: the text is the revision
   message, which names the change the ID belongs to.
"""

import ast
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "packages" / "bundlemcp" / "bundlemcp"
SETTINGS = PACKAGE / "application" / "settings" / "settings.py"
SPEC = ROOT / "spec"

# Markdown this repository owns; a package manager's vendored docs would
# otherwise contribute their own CVE and licence identifiers as "requirement IDs".
IGNORED = {"node_modules", ".vitepress", "dist", ".venv"}

DOC_SOURCES = sorted(
    p
    for p in [
        *(ROOT / "docs").rglob("*.md"),
        *(ROOT / ".claude" / "docs").glob("*.md"),
        ROOT / "CLAUDE.md",
        ROOT / "CONTRIBUTING.md",
        ROOT / "README.md",
    ]
    if IGNORED.isdisjoint(p.parts)
)

ENV_VAR = re.compile(r"BUNDLEMCP_[A-Z0-9_]+")
REQUIREMENT_ID = re.compile(r"\b([A-Z]{2,6})-([0-9]+[a-z]?)\b")

# Env vars that are deliberately not Settings fields.
ENV_EXEMPT = {
    "BUNDLEMCP_INTEGRATION",  # a pytest gate, read by tests/integration/conftest.py
    "BUNDLEMCP_OIDC_",  # a prefix fragment, quoted in spec/21
}
# Prefixes that look like requirement IDs but are not.
ID_EXEMPT_PREFIXES = {"ADR", "BSD", "MPL", "MIT", "RFC", "SHA", "UTF", "HTTP", "API", "CI"}


def settings_fields() -> set[str]:
    """The env var name of every field on Settings."""
    tree = ast.parse(SETTINGS.read_text())
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "Settings":
            for statement in node.body:
                if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
                    names.add(f"BUNDLEMCP_{statement.target.id.upper()}")
    return names


def documented_text() -> str:
    return "\n".join(p.read_text() for p in DOC_SOURCES if p.exists())


def spec_ids() -> set[str]:
    return {
        f"{m.group(1)}-{m.group(2)}"
        for path in SPEC.glob("*.md")
        for m in REQUIREMENT_ID.finditer(path.read_text())
    }


def ids_in_docstrings() -> list[str]:
    """Every docstring or Pydantic description carrying a requirement ID."""
    found: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        if "migrations/versions" in path.as_posix():
            continue
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:  # pragma: no cover - the suite would already fail
            continue
        rel = path.relative_to(ROOT)
        for node in ast.walk(tree):
            if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
                text = ast.get_docstring(node)
                if text and (hits := _real_ids(text)):
                    where = getattr(node, "name", "module")
                    found.append(f"{rel}:{node.body[0].lineno}: docstring of {where} cites {hits}")
            if isinstance(node, ast.keyword) and node.arg == "description":
                if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    if hits := _real_ids(node.value.value):
                        found.append(f"{rel}:{node.value.lineno}: description cites {hits}")
    return found


def _real_ids(text: str) -> str:
    hits = {
        f"{m.group(1)}-{m.group(2)}"
        for m in REQUIREMENT_ID.finditer(text)
        if m.group(1) not in ID_EXEMPT_PREFIXES
    }
    return ", ".join(sorted(hits))


def main() -> int:
    problems: list[str] = []
    text = documented_text()

    fields = settings_fields()
    mentioned = {v for v in ENV_VAR.findall(text) if v not in ENV_EXEMPT and not v.endswith("_")}
    for name in sorted(mentioned - fields):
        problems.append(f"documented but not a Settings field: {name}")
    for name in sorted(fields - mentioned):
        problems.append(f"a Settings field nobody documents: {name}")

    known = spec_ids()
    cited = {
        f"{m.group(1)}-{m.group(2)}"
        for m in REQUIREMENT_ID.finditer(text)
        if m.group(1) not in ID_EXEMPT_PREFIXES
    }
    for missing in sorted(cited - known):
        problems.append(f"cited in the docs but absent from spec/: {missing}")

    problems.extend(ids_in_docstrings())

    if problems:
        sys.stderr.write("\n".join(f"  {p}" for p in problems))
        sys.stderr.write(f"\n\n{len(problems)} settings/requirement-ID problem(s).\n")
        return 1
    sys.stderr.write(
        f"{len(fields)} settings documented both ways, {len(cited)} requirement IDs resolve, "
        "no IDs in docstrings or descriptions.\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
