#!/usr/bin/env python3
"""Write a pull request's changelog entry text with Claude, from its diff and description.

    ANTHROPIC_API_KEY=... python3 tools/changelog_writer.py --title ... --number 140 \\
        --url ... --body-file body.md --diff-file pr.diff > text.md

Prints the entry's sections (``### Added`` ... with bullets), each bullet linking
the pull request. The title only decides the version; this text says what a
user, operator or integrator gets. Exits 1 without printing when the key is
missing or the call fails, so the caller can fall back to the title.

The diff and description are the author's and may carry instructions; the model
can only answer through a fixed schema of short bullets, and the result is
checked before it is printed.
"""

import argparse
import json
import os
import re
import sys
import textwrap
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
MODEL = "claude-sonnet-5-5"
MAX_DIFF = 150_000
WIDTH = 120
EXCLUDED = (
    "uv.lock",
    "apps/web/package-lock.json",
    "docs/package-lock.json",
    "apps/web/openapi.json",
    "apps/web/types/api.d.ts",
    "CHANGELOG.md",
)
TOOL = "write_changelog_entry"
FILE_HEADER = re.compile(r"^diff --git a/(\S+) b/", re.MULTILINE)
INSTRUCTIONS = (Path(__file__).parent / "changelog_writer_prompt.md").read_text()

Bullet = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=400, pattern=r"^[^#\n<>]"),
]


class EntryDraft(BaseModel):
    """The entry's text as the model returns it, before rendering."""

    model_config = ConfigDict(extra="forbid")

    added: list[Bullet] = Field(default_factory=list, max_length=8, description="New capabilities")
    changed: list[Bullet] = Field(
        default_factory=list, max_length=8, description="Behaviour that works differently"
    )
    fixed: list[Bullet] = Field(
        default_factory=list, max_length=8, description="Behaviour that was wrong and is right"
    )
    security: list[Bullet] = Field(
        default_factory=list, max_length=8, description="Vulnerabilities closed, defences added"
    )
    breaking: str = Field(
        default="",
        max_length=400,
        pattern=r"^[^#\n<>]*$",
        description="What a caller, operator or deployment must do; empty when nothing breaks",
    )

    @property
    def is_empty(self) -> bool:
        return not (self.added or self.changed or self.fixed or self.security or self.breaking)


def tool_schema() -> dict:
    bullets = {"type": "array", "items": {"type": "string", "maxLength": 400}, "maxItems": 8}
    return {
        "name": TOOL,
        "description": "Record the changelog entry for this pull request.",
        "input_schema": {
            "type": "object",
            "properties": {
                "added": bullets,
                "changed": bullets,
                "fixed": bullets,
                "security": bullets,
                "breaking": {"type": "string", "maxLength": 400},
            },
            "required": ["added", "changed", "fixed", "security", "breaking"],
            "additionalProperties": False,
        },
    }


def filtered_diff(diff: str) -> str:
    """The diff without generated and lock files, cut to a size the call can carry."""
    starts = [match.start() for match in FILE_HEADER.finditer(diff)]
    kept = []
    for start, end in zip(starts, [*starts[1:], len(diff)], strict=False):
        section = diff[start:end]
        header = FILE_HEADER.match(section)
        if header is not None and header.group(1) in EXCLUDED:
            continue
        kept.append(section)
    text = "".join(kept)
    if len(text) > MAX_DIFF:
        text = text[:MAX_DIFF] + "\n[the diff was cut here; it continues]\n"
    return text


def user_message(title: str, body: str, diff: str) -> str:
    return (
        f"Pull request title: {title}\n\n"
        f"<description>\n{body.strip()}\n</description>\n\n"
        f"<diff>\n{filtered_diff(diff)}\n</diff>"
    )


def _post(payload: dict, api_key: str) -> dict:
    request = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode(),
        headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": API_VERSION,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        try:
            reason = json.loads(exc.read())["error"]["message"]
        except (ValueError, KeyError, TypeError):
            reason = exc.reason
        raise ValueError(f"the API answered {exc.code}: {reason}") from exc


def request_draft(
    api_key: str,
    title: str,
    body: str,
    diff: str,
    *,
    post: Callable[[dict, str], dict] = _post,
) -> EntryDraft:
    """Ask the model for the entry; raises ValueError when the answer is unusable."""
    payload = {
        "model": MODEL,
        "max_tokens": 2000,
        "system": INSTRUCTIONS,
        "tools": [tool_schema()],
        "tool_choice": {"type": "tool", "name": TOOL},
        "messages": [{"role": "user", "content": user_message(title, body, diff)}],
    }
    answer = post(payload, api_key)
    for block in answer.get("content", []):
        if block.get("type") == "tool_use" and block.get("name") == TOOL:
            try:
                draft = EntryDraft.model_validate(block.get("input"))
            except ValidationError as exc:
                raise ValueError(f"the entry did not match its schema: {exc}") from exc
            if draft.is_empty:
                raise ValueError("the entry has no bullets")
            return draft
    raise ValueError("the answer carried no entry")


def _bullet(text: str, link: str) -> str:
    sentence = text if text[-1] in ".!?" else f"{text}."
    return textwrap.fill(
        f"- {sentence} {link}",
        width=WIDTH,
        subsequent_indent="  ",
        break_long_words=False,
        break_on_hyphens=False,
    )


def render(draft: EntryDraft, number: int, url: str) -> str:
    """The entry's Markdown: a section per non-empty kind, each bullet linking the pull request."""
    link = f"([#{number}]({url}))"
    changed = list(draft.changed)
    if draft.breaking:
        changed.insert(0, f"**Breaking:** {draft.breaking}")
    sections = [
        ("Added", draft.added),
        ("Changed", changed),
        ("Fixed", draft.fixed),
        ("Security", draft.security),
    ]
    parts = [
        f"### {name}\n\n" + "\n".join(_bullet(item, link) for item in items)
        for name, items in sections
        if items
    ]
    return "\n\n".join(parts) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--title", required=True)
    parser.add_argument("--number", type=int, required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--body-file", type=Path, required=True)
    parser.add_argument("--diff-file", type=Path, required=True)
    args = parser.parse_args()
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        sys.stderr.write("ANTHROPIC_API_KEY is not set; no entry text written\n")
        return 1
    try:
        draft = request_draft(
            api_key, args.title, args.body_file.read_text(), args.diff_file.read_text()
        )
    except (ValueError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"no entry text written: {exc}\n")
        return 1
    sys.stdout.write(render(draft, args.number, args.url))
    return 0


if __name__ == "__main__":
    sys.exit(main())
