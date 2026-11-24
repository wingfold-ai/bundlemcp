"""Every image the Dockerfiles and the compose stack use is pinned by tag and digest (DEP-15),
and the stack runs nothing CI cannot build or pull (DEP-16)."""

import pathlib
import re

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[4]

FROM = re.compile(r"^FROM\s+(?:--platform=\S+\s+)?(?P<image>\S+)(?:\s+AS\s+(?P<alias>\S+))?", re.I)
COPY_FROM = re.compile(r"^COPY\s+(?:--\S+\s+)*?--from=(?P<image>\S+)", re.I)
SERVICE = re.compile(r"^  (?P<name>[A-Za-z0-9_.-]+):\s*$")
IMAGE = re.compile(r"^\s+image:\s*(?P<image>\S+)")


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

    An image taken from a variable counts by its default, whatever profile the service is in.
    """
    found: list[tuple[int, str]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if named := IMAGE.match(line):
            image = named.group("image").strip("'\"")
            if not is_pinned(image):
                found.append((number, image))
    return found


def dockerfiles() -> list[pathlib.Path]:
    return sorted(
        {
            *ROOT.glob("apps/*/Dockerfile"),
            *ROOT.glob("examples/*/Dockerfile"),
            *ROOT.glob("deploy/*/Dockerfile"),
        }
    )


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
    """DEP-15: a tag without a digest is reported in a Dockerfile and in a compose file, also as
    a variable's default under any profile; a digest and a stage alias are not."""
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
        "  chosen:\n"
        "    image: ${CHOSEN_IMAGE:-ghcr.io/x/y:latest}\n"
        "    profiles: [extra]\n"
        "  pinned:\n"
        f"    image: ${{PINNED_IMAGE:-ghcr.io/x/z:1.0{digest}}}\n"
    )
    assert compose_floating(compose) == [
        (3, "example/image:latest"),
        (7, "${CHOSEN_IMAGE:-ghcr.io/x/y:latest}"),
    ]


class ComposeLoader(yaml.SafeLoader):
    """Reads compose files, whose merge tags (``!override``, ``!reset``) keep their value."""


def _untagged(loader: yaml.SafeLoader, suffix: str, node: yaml.Node) -> object:
    if isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node, deep=True)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node, deep=True)
    return loader.construct_scalar(node)


ComposeLoader.add_multi_constructor("!", _untagged)


def unrunnable_services(compose: dict, base: pathlib.Path) -> list[str]:
    """Services CI could not start: no image, build or extended service, or a build outside the
    repository."""
    problems: list[str] = []
    for name, service in compose.get("services", {}).items():
        build = service.get("build")
        if build is not None:
            context = build if isinstance(build, str) else build.get("context", ".")
            directory = (base / context).resolve()
            if not directory.is_dir() or not directory.is_relative_to(ROOT):
                problems.append(
                    f"{name}: builds from {context}, not a directory of this repository"
                )
        elif "image" not in service and "extends" not in service:
            problems.append(f"{name}: neither builds an image nor names one")
    return problems


def test_dep16_every_service_is_built_here_or_pulled_pinned():
    """DEP-16: every service of the development compose files builds from a directory of this
    repository or names an image, which the DEP-15 test above holds to a digest."""
    problems = [
        f"{path.relative_to(ROOT)}: {problem}"
        for path in compose_files()
        for problem in unrunnable_services(
            yaml.load(path.read_text(), Loader=ComposeLoader),  # noqa: S506 - a SafeLoader subclass
            path.parent,
        )
    ]
    assert not problems, "\n".join(problems)


def test_dep16_the_check_catches_a_build_outside_the_repository(tmp_path):
    """DEP-16: a build context outside the repository, or a service with neither build nor
    image, is reported; a build from an example directory is not."""
    compose = {
        "services": {
            "local": {"build": "../examples/echo-mcp"},
            "elsewhere": {"build": {"context": str(tmp_path)}},
            "empty": {"restart": "always"},
        }
    }
    assert unrunnable_services(compose, ROOT / "deploy") == [
        f"elsewhere: builds from {tmp_path}, not a directory of this repository",
        "empty: neither builds an image nor names one",
    ]
