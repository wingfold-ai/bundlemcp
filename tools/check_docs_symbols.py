#!/usr/bin/env python3
"""Fail when the living documentation names a symbol or module path that no longer exists.

This is the check that catches rename drift. When #44 renamed ``McpEdge`` to
``McpGatewayRouter``, three rule files kept instructing the reader to register
new methods on a class with zero occurrences in the tree — and nothing noticed,
because ``docs/arc42/``, ``docs/adr/`` and every README are excluded from the
VitePress build that link-checks the rest of the documentation.

Three kinds of reference are checked:

* Backticked ``CamelCase`` identifiers must be defined somewhere under the
  package, or be listed in ``ALLOWED`` as an external or illustrative name.
* Backticked paths that look like a module or package under ``bundlemcp/`` must
  exist, allowing for the ``packages/bundlemcp/bundlemcp/`` prefix being elided.
* Names in ``RETIRED`` must not appear at all, backticked or not.

``docs/adr/`` is deliberately **not** checked: ADRs are append-only records of
what was decided at a point in time, and naming a symbol that has since been
renamed is correct behaviour for them.
"""

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "packages" / "bundlemcp" / "bundlemcp"

# The documentation that describes the code as it is *now*.
LIVING_DOCS = [
    ROOT / "CLAUDE.md",
    ROOT / "CONTRIBUTING.md",
    ROOT / "README.md",
    ROOT / "packages" / "bundlemcp" / "README.md",
    *sorted((ROOT / ".claude" / "docs").glob("*.md")),
    *sorted((ROOT / "docs" / "arc42").glob("*.md")),
]

# Names that are real but defined outside this package.
ALLOWED = {
    # stdlib and typing
    "Protocol",
    "BaseModel",
    "ConfigDict",
    "Field",
    "SQLModel",
    "StrEnum",
    "Literal",
    "Annotated",
    "Exception",
    "ValidationError",
    "SchemaError",
    "ValueError",
    "None",
    "True",
    "False",
    "Mapping",
    "Sequence",
    "Iterable",
    "Optional",
    "Union",
    "Any",
    # frameworks and libraries
    "FastAPI",
    "FastMCP",
    "APIRouter",
    "Depends",
    "Request",
    "Response",
    "JSONResponse",
    "HTTPException",
    "CORSMiddleware",
    "Starlette",
    "SQLAlchemy",
    "Alembic",
    "Pydantic",
    "Nuxt",
    "Valkey",
    "Redis",
    "Postgres",
    "PostgreSQL",
    "SQLite",
    "Keycloak",
    "Caddy",
    "Docker",
    "Dockerfile",
    "Python",
    "TypeScript",
    "JavaScript",
    "JSON",
    "YAML",
    "LikeC4",
    "Playwright",
    "Prometheus",
    "Fernet",
    "OAuth",
    "OpenAPI",
    "Markdown",
    "SkipValidation",
    "AnyHttpUrl",
    "MADR",
    "GitHub",
    "Claude",
    "ChatGPT",
    # names used illustratively in the rule docs, not claimed to exist
    "MyApp",
    "LedgerHook",
    "CallHandle",
    "RateResult",
    "NewAuthService",
    "ImprovedCallHandler",
    "StreamedCallHandler",
    "OidcSessionService",
    "AuditSink",
    "BundleView",
    # counter-examples: names the conventions forbid, so their absence is the point
    "Edge",
    "Core",
    "Base",
    "Handler",
    "Service",
    "Uninitialized",
    "Active",
    "Closed",
}

# A documented path is treated as a module path only when it starts in one of these,
# or ends in .py. Without this, JSON-RPC method names such as `tools/call` and
# `tools/list` read as module paths. ("tools/" is absent for exactly that reason;
# this repo's own tools/ scripts are always written with their .py suffix.)
PACKAGE_ROOTS = (
    "domain/",
    "application/",
    "infrastructure/",
    "api/",
    "main/",
    "packages/",
    "apps/",
    "deploy/",
    "openspec/",
    "docs/",
    "tests/",
    ".claude/",
)

# Names a refactor retired. Unlike the checks below, these are matched anywhere in
# the text, not only inside backticks: the occurrence that survived longest after
# #44 was an unbackticked `McpEdgeAssembly` inside a directory tree, which no
# backtick-scoped check would ever have seen. Add a row whenever a rename lands.
RETIRED = {
    "McpEdgeAssembly": "McpGatewayAssembly",
    "McpEdge": "McpGatewayRouter",
    "GatewayRuntime": "AppContainer",
    "Era.MODERN": "ProtocolEra.STATELESS",
    "Era.HANDSHAKE": "ProtocolEra.SESSION",
}

CAMEL = re.compile(r"`([A-Z][A-Za-z0-9]{3,})`")
MODULE_PATH = re.compile(r"`((?:[a-z_][a-z0-9_]*/)+[a-z_][a-z0-9_]*(?:\.py)?)`")


def defined_names() -> set[str]:
    """Every class, enum member alias and assignment target the package defines."""
    names: set[str] = set()
    pattern = re.compile(r"^\s*(?:class\s+([A-Z][A-Za-z0-9]*)|([A-Z][A-Za-z0-9_]*)\s*[:=])")
    for path in PACKAGE.rglob("*.py"):
        for line in path.read_text().splitlines():
            if match := pattern.match(line):
                names.add(match.group(1) or match.group(2))
    return names


def path_exists(candidate: str) -> bool:
    """Whether a documented module path resolves, with or without the package prefix."""
    trimmed = candidate.rstrip("/")
    for base in (PACKAGE, ROOT, ROOT / "packages" / "bundlemcp"):
        target = base / trimmed
        if target.exists() or target.with_suffix(".py").exists():
            return True
    return False


def main() -> int:
    known = defined_names()
    problems: list[str] = []

    for doc in LIVING_DOCS:
        if not doc.exists():
            problems.append(f"{doc.relative_to(ROOT)}: listed as living documentation but missing")
            continue
        text = doc.read_text()
        rel = doc.relative_to(ROOT)
        for number, line in enumerate(text.splitlines(), start=1):
            if "❌" in line:
                # A line showing the rejected spelling beside the correct one has
                # to name the retired symbol; that is what makes it teachable.
                continue
            for retired, replacement in RETIRED.items():
                # Longest-first so `McpEdgeAssembly` is not reported twice.
                if retired in line and not any(
                    longer != retired and retired in longer and longer in line for longer in RETIRED
                ):
                    problems.append(f"{rel}:{number}: `{retired}` was renamed to `{replacement}`")
            for name in CAMEL.findall(line):
                if name not in known and name not in ALLOWED:
                    problems.append(f"{rel}:{number}: `{name}` is defined nowhere in the package")
            for candidate in MODULE_PATH.findall(line):
                looks_like_a_path = candidate.endswith(".py") or candidate.startswith(PACKAGE_ROOTS)
                if looks_like_a_path and not path_exists(candidate):
                    problems.append(f"{rel}:{number}: `{candidate}` does not exist")

    if problems:
        sys.stderr.write("\n".join(f"  {p}" for p in problems))
        sys.stderr.write(
            f"\n\n{len(problems)} stale reference(s) in the living documentation.\n"
            "Either the docs are out of date, or an external name belongs in ALLOWED.\n"
        )
        return 1
    sys.stderr.write(f"No stale symbols or paths across {len(LIVING_DOCS)} living documents.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
