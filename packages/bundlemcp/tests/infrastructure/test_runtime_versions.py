"""The Python and Node versions the repository ships, and the images and CI jobs that use them."""

import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[4]

PYTHON_IMAGES = [
    "apps/gateway/Dockerfile",
    "examples/conformance-mcp/Dockerfile",
    "examples/echo-mcp/Dockerfile",
    "examples/identity-demo-mcp/Dockerfile",
    "examples/oauth-demo-mcp/Dockerfile",
]
IMAGE_VERSION = re.compile(r"\b(?:python:|uv:python)(\d+\.\d+)")
WORKFLOW_VERSION = re.compile(r"python-version:\s*[\"']?(\d+\.\d+)")
NODE_WORKFLOW_VERSION = re.compile(r"node-version:\s*[\"']?(\d+)")
NODE_IMAGE_VERSION = re.compile(r"^FROM\s+node:(\d+)", re.MULTILINE)
MIN_NODE = 24


def declared() -> str:
    return (ROOT / ".python-version").read_text().strip()


def references() -> list[tuple[str, str]]:
    """Every (file, version) pair naming a Python version in an image or a CI job."""
    found = []
    dockerfiles = sorted({*ROOT.glob("apps/*/Dockerfile"), *ROOT.glob("examples/*/Dockerfile")})
    workflows = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
    for path, pattern in [(p, IMAGE_VERSION) for p in dockerfiles] + [
        (p, WORKFLOW_VERSION) for p in workflows
    ]:
        for version in pattern.findall(path.read_text()):
            found.append((str(path.relative_to(ROOT)), version))
    return found


def test_arc2_images_and_ci_use_the_declared_python():
    """ARC-2: every image and CI job names the Python version .python-version declares."""
    mismatched = [(f, v) for f, v in references() if v != declared()]
    assert not mismatched, f"expected Python {declared()}, found: {mismatched}"


def test_arc2_every_python_image_names_a_version():
    """ARC-2: a Python image whose reference cannot be read fails rather than passing unchecked."""
    named = {f for f, _ in references()}
    missing = [f for f in PYTHON_IMAGES if f not in named]
    assert not missing, f"no Python version found in: {missing}"


MATRIX_VERSIONS = re.compile(r"^\s*python:\s*\[([^\]]*)\]", re.MULTILINE)
REQUIRES_PYTHON = re.compile(r'^requires-python\s*=\s*">=(\d+)\.(\d+)"', re.MULTILINE)


def supported() -> list[str]:
    """Every minor version from the requires-python floor up to the declared one."""
    floor = REQUIRES_PYTHON.search((ROOT / "pyproject.toml").read_text())
    assert floor, "pyproject.toml declares no requires-python floor"
    major, lowest = int(floor.group(1)), int(floor.group(2))
    newest = int(declared().split(".")[1])
    return [f"{major}.{minor}" for minor in range(lowest, newest + 1)]


def test_arc2_ci_tests_every_supported_python():
    """ARC-2: the backend test matrix covers every Python version requires-python allows."""
    matrix = MATRIX_VERSIONS.search((ROOT / ".github/workflows/ci.yml").read_text())
    assert matrix, "ci.yml has no python matrix"
    tested = re.findall(r"\d+\.\d+", matrix.group(1))
    assert tested == supported(), f"expected {supported()}, CI tests {tested}"


def test_arc2_packages_share_one_python_floor():
    """ARC-2: the workspace and the library declare the same requires-python."""
    floors = {
        REQUIRES_PYTHON.search((ROOT / path).read_text()).group(0)
        for path in ["pyproject.toml", "packages/bundlemcp/pyproject.toml"]
    }
    assert len(floors) == 1, floors


def node_versions(text: str) -> list[int]:
    """Every major Node version a workflow sets up."""
    return [int(v) for v in NODE_WORKFLOW_VERSION.findall(text)]


def test_arc2_no_ci_job_runs_an_older_node():
    """ARC-2: every node-version a workflow sets is 24 or later."""
    workflows = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
    older = [
        (str(p.relative_to(ROOT)), v)
        for p in workflows
        for v in node_versions(p.read_text())
        if v < MIN_NODE
    ]
    assert not older, f"expected Node {MIN_NODE} or later, found: {older}"


def test_arc2_the_check_catches_a_downgraded_workflow():
    """ARC-2: a workflow pinned to Node 22 is read as 22, so the check above would fail on it."""
    assert node_versions('- uses: actions/setup-node@x\n  with:\n    node-version: "22"\n') == [22]


def test_arc2_web_app_declares_and_builds_on_node_24_or_later():
    """ARC-2: apps/web declares node >=24 in engines, enforced on install, and its image runs
    a Node of at least that version."""
    package = json.loads((ROOT / "apps/web/package.json").read_text())
    assert package["engines"]["node"] == f">={MIN_NODE}"
    assert "engine-strict=true" in (ROOT / "apps/web/.npmrc").read_text().split()
    images = [
        int(v) for v in NODE_IMAGE_VERSION.findall((ROOT / "apps/web/Dockerfile").read_text())
    ]
    assert images and min(images) >= MIN_NODE
