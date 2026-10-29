"""Every image the Dockerfiles and the compose stack use is pinned by tag and digest (DEP-15)."""

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[4]

FROM = re.compile(r"^FROM\s+(?:--platform=\S+\s+)?(?P<image>\S+)(?:\s+AS\s+(?P<alias>\S+))?", re.I)
COPY_FROM = re.compile(r"^COPY\s+(?:--\S+\s+)*?--from=(?P<image>\S+)", re.I)
SERVICE = re.compile(r"^  (?P<name>[A-Za-z0-9_.-]+):\s*$")
IMAGE = re.compile(r"^\s+image:\s*(?P<image>\S+)")
PROFILES = re.compile(r"^\s+profiles:\s*\[(?P<profiles>[^\]]*)\]")
OPERATOR_CHOSEN = re.compile(r"^\$\{[A-Z0-9_]+:-")
FLEET_PROFILE = "fleet"


def is_pinned(image: str) -> bool:
    return "@sha256:" in image


def dockerfile_floating(text: str) -> list[tuple[int, str]]:
    """``(line, image)`` for every image a Dockerfile builds or copies from without a digest.

    A ``FROM`` or ``COPY --from`` naming an earlier stage is not an image reference.
    """
    stages: set[str] = set()
    found: list[tuple[int, str]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        reference = FROM.match(line) or COPY_FROM.match(line)
        if reference is None:
            continue
        image = reference.group("image")
        if image.lower() not in stages and not image.isdigit() and not is_pinned(image):
            found.append((number, image))
        alias = reference.groupdict().get("alias")
        if alias:
            stages.add(alias.lower())
    return found


def compose_floating(text: str) -> list[tuple[int, str]]:
    """``(line, image)`` for every compose service image without a digest.

    The one exception is an image an operator chooses through a variable, for a
    service of the ``fleet`` profile, which the default stack never starts.
    """
    found: list[tuple[int, str, str]] = []
    profiles: dict[str, set[str]] = {}
    service = ""
    for number, line in enumerate(text.splitlines(), start=1):
        if heading := SERVICE.match(line):
            service = heading.group("name")
        elif listed := PROFILES.match(line):
            profiles[service] = {
                p.strip().strip("'\"") for p in listed.group("profiles").split(",")
            }
        elif named := IMAGE.match(line):
            image = named.group("image").strip("'\"")
            if not is_pinned(image):
                found.append((number, image, service))
    return [
        (number, image)
        for number, image, owner in found
        if not (OPERATOR_CHOSEN.match(image) and FLEET_PROFILE in profiles.get(owner, set()))
    ]


def dockerfiles() -> list[pathlib.Path]:
    return sorted({*ROOT.glob("apps/*/Dockerfile"), *ROOT.glob("examples/*/Dockerfile")})


def compose_files() -> list[pathlib.Path]:
    return sorted((ROOT / "deploy").glob("docker-compose*.yml"))


def test_dep15_every_image_is_pinned_by_digest():
    """DEP-15: every FROM, COPY --from image and compose image names a tag and a digest."""
    floating = [
        f"{path.relative_to(ROOT)}:{number}: {image}"
        for path in dockerfiles()
        for number, image in dockerfile_floating(path.read_text())
    ] + [
        f"{path.relative_to(ROOT)}:{number}: {image}"
        for path in compose_files()
        for number, image in compose_floating(path.read_text())
    ]
    assert dockerfiles() and compose_files()
    assert not floating, (
        "DEP-15: pin these images as <image>:<tag>@sha256:<digest> "
        "(docker buildx imagetools inspect <image>:<tag>):\n" + "\n".join(floating)
    )


def test_dep15_the_check_catches_a_floating_tag():
    """DEP-15: a tag without a digest is reported in a Dockerfile and in a compose file; a
    digest, a stage alias and an operator-chosen fleet image are not."""
    digest = "@sha256:" + "0" * 64
    dockerfile = (
        "FROM node:26-alpine AS build\n"
        "RUN npm ci\n"
        f"FROM python:3.15.1-slim-bookworm{digest}\n"
        "COPY --from=build /app /app\n"
        "COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /usr/local/bin/\n"
        "FROM build\n"
    )
    assert dockerfile_floating(dockerfile) == [
        (1, "node:26-alpine"),
        (5, "ghcr.io/astral-sh/uv:0.13.5"),
    ]
    compose = (
        "services:\n"
        "  app:\n"
        "    image: example/image:latest\n"
        "  db:\n"
        f"    image: postgres:17-alpine{digest}\n"
        "  seo-psi:\n"
        "    image: ${SEO_PSI_IMAGE:-ghcr.io/x/y:latest}\n"
        "    profiles: [fleet]\n"
        "  other:\n"
        "    image: ${OTHER_IMAGE:-ghcr.io/x/z:latest}\n"
    )
    assert compose_floating(compose) == [
        (3, "example/image:latest"),
        (10, "${OTHER_IMAGE:-ghcr.io/x/z:latest}"),
    ]
