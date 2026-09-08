#!/usr/bin/env python3
"""Scan a source tree for cross-layer imports and flag dependency-rule violations.

Usage:
    python scan_imports.py <src_root> --mapping mapping.json [--out edges.json] [--frameworks extra,names]

mapping.json:
    {
      "domain": ["src/domain"],
      "application": ["src/application", "src/services"],
      "infrastructure": ["src/infrastructure", "src/db"],
      "api": ["src/api", "src/routes"],
      "composition_root": ["src/main.py"]
    }
Prefixes are relative to <src_root>'s parent (i.e. include the src folder name) OR relative to
<src_root> itself — both are tried.

Heuristic, stdlib only. Supports: Python, TypeScript/JavaScript, Go, Java, Kotlin, C#.
It resolves an import to a layer by checking whether the imported path/module string contains
one of the mapping prefixes (path separators normalised to '/', dots treated as '/').
Framework detection: imports whose first segment is in a known framework/ORM/SDK list.

Output: JSON with `edges` (all cross-layer or framework edges) and `summary`.
Each edge: file, line, from_layer, from_module, to_layer, to_module, import, violation, reason.
"""
import argparse
import json
import os
import re
import sys
from collections import Counter

LAYERS = ("domain", "application", "infrastructure", "api", "composition_root")

# who may import whom
ALLOWED = {
    "domain": {"domain"},
    "application": {"domain", "application"},
    "infrastructure": {"domain", "application", "infrastructure"},
    "api": {"domain", "application", "api"},
    "composition_root": set(LAYERS),
}
FRAMEWORK_ALLOWED = {"infrastructure", "api", "composition_root"}

FRAMEWORKS = {
    # python
    "sqlalchemy", "django", "flask", "fastapi", "starlette", "pydantic", "tortoise", "peewee",
    "psycopg2", "psycopg", "asyncpg", "pymongo", "motor", "redis", "boto3", "stripe", "requests",
    "httpx", "aiohttp", "celery", "kafka", "aiokafka", "pika", "grpc", "graphene", "strawberry",
    # js/ts
    "express", "koa", "fastify", "nestjs", "@nestjs", "typeorm", "prisma", "@prisma", "mongoose",
    "sequelize", "knex", "pg", "mysql2", "ioredis", "axios", "node-fetch", "aws-sdk", "@aws-sdk",
    "kafkajs", "amqplib", "next", "react",
    # go
    "gorm.io", "github.com/gin-gonic", "github.com/labstack/echo", "github.com/go-chi",
    "github.com/jackc/pgx", "database/sql", "go.mongodb.org", "github.com/redis", "net/http",
    "github.com/segmentio/kafka-go", "google.golang.org/grpc",
    # java/kotlin
    "org.springframework", "javax.persistence", "jakarta.persistence", "org.hibernate",
    "javax.ws.rs", "jakarta.ws.rs", "io.micronaut", "io.quarkus", "org.jooq", "com.mongodb",
    "redis.clients", "com.stripe", "org.apache.kafka",
    # c#
    "Microsoft.EntityFrameworkCore", "Microsoft.AspNetCore", "Dapper", "MongoDB.Driver",
    "StackExchange.Redis", "Stripe", "Npgsql", "System.Data",
}

EXT_LANG = {
    ".py": "python", ".ts": "ts", ".tsx": "ts", ".js": "ts", ".jsx": "ts", ".mjs": "ts",
    ".go": "go", ".java": "java", ".kt": "kotlin", ".cs": "csharp",
}

IMPORT_RE = {
    "python": [re.compile(r"^\s*from\s+([\w\.]+)\s+import\b"), re.compile(r"^\s*import\s+([\w\.]+)")],
    "ts": [re.compile(r"""^\s*import\s+(?:[^'"]*?\s+from\s+)?['"]([^'"]+)['"]"""),
           re.compile(r"""require\(\s*['"]([^'"]+)['"]\s*\)""")],
    "go": [re.compile(r'^\s*"([^"]+)"\s*$'), re.compile(r'^\s*import\s+"([^"]+)"')],
    "java": [re.compile(r"^\s*import\s+(?:static\s+)?([\w\.]+)")],
    "kotlin": [re.compile(r"^\s*import\s+([\w\.]+)")],
    "csharp": [re.compile(r"^\s*using\s+(?:static\s+)?([\w\.]+)\s*;")],
}

SKIP_DIRS = {"node_modules", ".git", "dist", "build", "target", "bin", "obj", "__pycache__",
             ".venv", "venv", "vendor", ".next", "coverage"}


def norm(p):
    return p.replace("\\", "/").replace(".", "/").strip("/")


def load_mapping(path):
    with open(path) as f:
        raw = json.load(f)
    mapping = {}
    for layer in LAYERS:
        mapping[layer] = [norm(x) for x in raw.get(layer, [])]
    return mapping


def layer_of(path_like, mapping, root_name):
    """Return (layer, module) for a normalised path/module string, or (None, None)."""
    p = norm(path_like)
    candidates = [p]
    if root_name and not p.startswith(root_name + "/"):
        candidates.append(root_name + "/" + p)
    best = (None, None, -1)
    for layer, prefixes in mapping.items():
        for pref in prefixes:
            for c in candidates:
                # prefix match on a path boundary, anywhere in the string (handles relative imports resolved loosely)
                idx = c.find(pref)
                if idx == -1:
                    continue
                if idx > 0 and c[idx - 1] != "/":
                    continue
                end = idx + len(pref)
                if end < len(c) and c[end] != "/":
                    continue
                if len(pref) > best[2]:
                    rest = c[end:].strip("/")
                    module = rest.split("/")[0] if rest else os.path.basename(pref)
                    best = (layer, module, len(pref))
    return best[0], best[1]


def is_framework(imp, extra):
    s = imp.replace("\\", "/")
    first = s.split("/")[0].split(".")[0] if not s.startswith("@") else "/".join(s.split("/")[:2])
    full_dotted = s
    for fw in FRAMEWORKS | extra:
        if s == fw or s.startswith(fw + "/") or s.startswith(fw + ".") or full_dotted.startswith(fw) or first == fw:
            return True
    return False


def resolve_relative(imp, file_rel):
    """Resolve ./ and ../ imports (ts) or leading-dot python imports against the file's folder."""
    folder = os.path.dirname(file_rel).replace("\\", "/")
    if imp.startswith("."):
        if "/" in imp:  # ts style
            return norm(os.path.normpath(os.path.join(folder, imp)))
        # python relative: count leading dots
        dots = len(imp) - len(imp.lstrip("."))
        base = folder
        for _ in range(dots - 1):
            base = os.path.dirname(base)
        rest = imp.lstrip(".").replace(".", "/")
        return norm(os.path.join(base, rest))
    return imp


def scan(root, mapping, extra_fw):
    root = os.path.abspath(root)
    root_name = os.path.basename(root)
    parent = os.path.dirname(root)
    edges = []
    files_by_layer = Counter()
    unmapped = []

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for fn in filenames:
            ext = os.path.splitext(fn)[1]
            lang = EXT_LANG.get(ext)
            if not lang:
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, parent).replace("\\", "/")
            if "test" in rel.lower() or "spec." in fn.lower():
                continue
            src_layer, src_module = layer_of(rel, mapping, root_name)
            if not src_layer:
                unmapped.append(rel)
                continue
            files_by_layer[src_layer] += 1
            try:
                with open(full, encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()
            except OSError:
                continue
            in_go_import_block = False
            for ln, line in enumerate(lines, 1):
                if lang == "go":
                    if re.match(r"^\s*import\s*\(", line):
                        in_go_import_block = True
                        continue
                    if in_go_import_block and line.strip() == ")":
                        in_go_import_block = False
                        continue
                    if not in_go_import_block and not line.lstrip().startswith("import"):
                        continue
                for rx in IMPORT_RE[lang]:
                    m = rx.search(line)
                    if not m:
                        continue
                    imp = m.group(1)
                    resolved = resolve_relative(imp, rel) if lang in ("python", "ts") else imp
                    dst_layer, dst_module = layer_of(resolved, mapping, root_name)
                    if dst_layer:
                        if dst_layer == src_layer:
                            continue
                        violation = dst_layer not in ALLOWED[src_layer]
                        reason = "" if not violation else f"{src_layer} may not import {dst_layer}"
                        edges.append(dict(file=rel, line=ln, from_layer=src_layer,
                                          from_module=f"{src_layer}/{src_module}",
                                          to_layer=dst_layer, to_module=f"{dst_layer}/{dst_module}",
                                          **{"import": imp}, violation=violation, reason=reason))
                    elif is_framework(imp, extra_fw):
                        violation = src_layer not in FRAMEWORK_ALLOWED
                        reason = "" if not violation else f"{src_layer} imports framework/ORM/SDK"
                        edges.append(dict(file=rel, line=ln, from_layer=src_layer,
                                          from_module=f"{src_layer}/{src_module}",
                                          to_layer="framework", to_module=imp,
                                          **{"import": imp}, violation=violation, reason=reason))
                    break
    return edges, files_by_layer, unmapped


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", help="source root to scan (e.g. src)")
    ap.add_argument("--mapping", required=True, help="layer mapping JSON")
    ap.add_argument("--out", default=None, help="write full JSON result here")
    ap.add_argument("--frameworks", default="", help="comma-separated extra framework/SDK import roots")
    args = ap.parse_args()

    mapping = load_mapping(args.mapping)
    extra = {x.strip() for x in args.frameworks.split(",") if x.strip()}
    edges, files_by_layer, unmapped = scan(args.root, mapping, extra)

    violations = [e for e in edges if e["violation"]]
    by_reason = Counter(e["reason"] for e in violations)
    summary = {
        "files_by_layer": dict(files_by_layer),
        "unmapped_files": len(unmapped),
        "cross_layer_edges": len(edges),
        "violations": len(violations),
        "violations_by_reason": dict(by_reason),
    }

    print(f"files by layer: {dict(files_by_layer)}")
    print(f"unmapped files: {len(unmapped)}" + (f" (e.g. {unmapped[:3]})" if unmapped else ""))
    print(f"cross-layer edges: {len(edges)}, violations: {len(violations)}")
    for reason, n in by_reason.most_common():
        print(f"  {n:4d}  {reason}")
    if violations:
        print("\nviolations:")
        for e in violations[:200]:
            print(f"  {e['file']}:{e['line']}  {e['from_layer']} -> {e['to_layer']}  ({e['import']})")
        if len(violations) > 200:
            print(f"  ... {len(violations) - 200} more")

    if args.out:
        with open(args.out, "w") as f:
            json.dump({"summary": summary, "edges": edges, "unmapped": unmapped}, f, indent=2)
        print(f"\nwrote {args.out}")

    sys.exit(1 if violations else 0)


if __name__ == "__main__":
    main()
