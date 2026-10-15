"""The changelog entry's text, written by a model from the pull request (DEP-12)."""

import importlib.util
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[4]
_spec = importlib.util.spec_from_file_location(
    "changelog_writer", ROOT / "tools/changelog_writer.py"
)
assert _spec is not None and _spec.loader is not None
writer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(writer)

URL = "https://github.com/wingfold-ai/bundlemcp/pull/140"

DIFF = """diff --git a/packages/bundlemcp/x.py b/packages/bundlemcp/x.py
+code
diff --git a/uv.lock b/uv.lock
+lock
diff --git a/CHANGELOG.md b/CHANGELOG.md
+entry
diff --git a/apps/web/openapi.json b/apps/web/openapi.json
+schema
"""


def _answer(entry: dict) -> dict:
    return {"content": [{"type": "tool_use", "name": writer.TOOL, "input": entry}]}


def _entry(**sections) -> dict:
    return {"added": [], "changed": [], "fixed": [], "security": [], "breaking": "", **sections}


def test_dep12_the_model_is_asked_through_a_forced_tool_with_the_filtered_diff():
    sent = {}

    def post(payload, api_key):
        sent.update(payload, api_key=api_key)
        return _answer(_entry(added=["Order a bundle's members by hand"]))

    writer.request_draft("key", "feat(bundles): Order", "Body", DIFF, post=post)
    assert sent["api_key"] == "key"
    assert sent["model"] == writer.MODEL
    assert sent["tool_choice"] == {"type": "tool", "name": writer.TOOL}
    message = sent["messages"][0]["content"]
    assert "+code" in message and "Body" in message
    assert "+lock" not in message and "+entry" not in message and "+schema" not in message


def test_dep12_a_long_diff_is_cut_and_says_so():
    diff = "diff --git a/x.py b/x.py\n" + "+" * (writer.MAX_DIFF + 10)
    assert writer.filtered_diff(diff).endswith("[the diff was cut here; it continues]\n")


def test_dep12_entry_renders_sections_with_the_link_on_every_bullet():
    draft = writer.EntryDraft(
        added=["Order a bundle's members by hand"],
        fixed=["Expired tokens are refused!"],
        breaking="Rename `BUNDLEMCP_X` to `BUNDLEMCP_Y`",
    )
    text = writer.render(draft, 140, URL)
    link = f"([#140]({URL}))"
    assert text == (
        f"### Added\n\n- Order a bundle's members by hand. {link}\n\n"
        f"### Changed\n\n- **Breaking:** Rename `BUNDLEMCP_X` to `BUNDLEMCP_Y`. {link}\n\n"
        f"### Fixed\n\n- Expired tokens are refused! {link}\n"
    )


def test_dep12_rendered_lines_stay_within_120_columns():
    draft = writer.EntryDraft(changed=["word " * 79 + "end"])
    lines = writer.render(draft, 140, URL).splitlines()
    assert max(len(line) for line in lines) <= 120
    assert all(line.startswith("  ") for line in lines[3:])


@pytest.mark.parametrize(
    "entry",
    [
        _entry(added=["# A heading"]),
        _entry(added=["<script>x</script>"]),
        _entry(added=["x" * 401]),
        _entry(added=["One"] * 9),
        _entry(breaking="two\nlines"),
        _entry(),
        {**_entry(added=["One"]), "removed": ["Two"]},
    ],
)
def test_dep12_an_entry_outside_the_schema_is_refused(entry):
    with pytest.raises(ValueError):
        writer.request_draft("key", "t", "", "", post=lambda payload, key: _answer(entry))


def test_dep12_an_answer_without_the_tool_call_is_refused():
    def post(payload, key):
        return {"content": [{"type": "text", "text": "### Added\n\n- Sure"}]}

    with pytest.raises(ValueError, match="no entry"):
        writer.request_draft("key", "t", "", "", post=post)


def test_dep12_without_a_key_nothing_is_written(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    (tmp_path / "body").write_text("")
    (tmp_path / "diff").write_text("")
    monkeypatch.setattr(
        "sys.argv",
        [
            "changelog_writer.py",
            "--title=feat(x): Y",
            "--number=1",
            f"--url={URL}",
            f"--body-file={tmp_path / 'body'}",
            f"--diff-file={tmp_path / 'diff'}",
        ],
    )
    assert writer.main() == 1
    assert capsys.readouterr().out == ""


def test_dep12_a_workspace_id_is_sent_when_set(monkeypatch):
    sent = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return b'{"content": []}'

    def urlopen(request, timeout):
        sent.update({key.lower(): value for key, value in request.header_items()})
        return Response()

    monkeypatch.setattr(writer.urllib.request, "urlopen", urlopen)
    monkeypatch.setenv("ANTHROPIC_WORKSPACE_ID", "wrkspc_1")
    writer._post({}, "key")
    assert sent["anthropic-workspace-id"] == "wrkspc_1"
    monkeypatch.delenv("ANTHROPIC_WORKSPACE_ID")
    sent.clear()
    writer._post({}, "key")
    assert "anthropic-workspace-id" not in sent
