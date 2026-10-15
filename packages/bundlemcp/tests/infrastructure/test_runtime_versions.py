"""The Python version the repository ships, and the images and CI jobs that must use it."""

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[4]

PYTHON_IMAGES = [
    "apps/gateway/Dockerfile",
    "examples/echo-mcp/Dockerfile",
    "examples/oauth-demo-mcp/Dockerfile",
]
IMAGE_VERSION = re.compile(r"\b(?:python:|uv:python)(\d+\.\d+)")
WORKFLOW_VERSION = re.compile(r"python-version:\s*[\"']?(\d+\.\d+)")


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
