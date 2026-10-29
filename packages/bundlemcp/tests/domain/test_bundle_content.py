"""Bundle-owned prompts and resources: the rules that hold without any storage."""

import uuid

import pytest
from bundlemcp.domain.bundles.bundle import Bundle
from bundlemcp.domain.bundles.bundle_capabilities import aggregate_capabilities
from bundlemcp.domain.bundles.bundle_content_limits import BundleContentLimits
from bundlemcp.domain.bundles.bundle_content_rejected import BundleContentRejected
from bundlemcp.domain.bundles.bundle_prompt import BundlePrompt
from bundlemcp.domain.bundles.bundle_resource import BundleResource
from bundlemcp.domain.bundles.bundle_resource_uri import (
    bundle_resource_name,
    bundle_resource_uri,
    is_bundle_uri,
)
from bundlemcp.domain.bundles.bundle_view import BundleView
from bundlemcp.domain.bundles.prompt_argument import PromptArgument
from bundlemcp.domain.bundles.prompt_listing import PromptListing
from bundlemcp.domain.bundles.prompt_message import PromptMessage
from bundlemcp.domain.bundles.prompt_role import PromptRole
from bundlemcp.domain.bundles.resource_listing import ResourceListing
from bundlemcp.domain.bundles.resource_mime_type import ResourceMimeType
from bundlemcp.domain.endpoints.endpoint import Endpoint
from bundlemcp.domain.shared.resource_names import BundleResourceName, PromptName
from pydantic import TypeAdapter, ValidationError

BUNDLE_ID = uuid.uuid4()


def _prompt(*messages: PromptMessage, arguments: list[PromptArgument] | None = None):
    return BundlePrompt(
        bundle_id=BUNDLE_ID, name="chart", arguments=arguments or [], messages=list(messages)
    )


def _user(text: str) -> PromptMessage:
    return PromptMessage(role=PromptRole.USER, text=text)


@pytest.mark.parametrize("name", ["chart", "make-chart", "chart_2"])
def test_prompt_name_accepts_plain_names(name):
    """BND-19"""
    assert TypeAdapter(PromptName).validate_python(name) == name


@pytest.mark.parametrize("name", ["python__chart", "a.b", "a/b", ""])
def test_prompt_name_rejects_prefix_separator_and_punctuation(name):
    """BND-19: no `__`, so a bundle prompt can never collide with a member's prefixed one."""
    with pytest.raises(ValidationError):
        TypeAdapter(PromptName).validate_python(name)


@pytest.mark.parametrize("name", ["style", "guides/style", "guides/v1.2/style.md"])
def test_resource_name_accepts_folders(name):
    """BND-23"""
    assert TypeAdapter(BundleResourceName).validate_python(name) == name


@pytest.mark.parametrize("name", ["/style", "guides/", "guides//style", "a b", ".hidden"])
def test_resource_name_rejects_malformed_paths(name):
    """BND-23"""
    with pytest.raises(ValidationError):
        TypeAdapter(BundleResourceName).validate_python(name)


def test_message_has_text_or_resource_not_both():
    """BND-20"""
    with pytest.raises(ValidationError):
        PromptMessage(role=PromptRole.USER, text="x", resource="style")
    with pytest.raises(ValidationError):
        PromptMessage(role=PromptRole.USER)


def test_render_substitutes_arguments_and_blanks_missing_optional_ones():
    """BND-20, BND-21"""
    prompt = _prompt(
        _user("Plot {{series}} as a {{kind}} chart.{{note}}"),
        arguments=[
            PromptArgument(name="series", required=True),
            PromptArgument(name="kind"),
            PromptArgument(name="note"),
        ],
    )
    rendered = prompt.render({"series": "revenue", "kind": "bar"})
    assert rendered[0].text == "Plot revenue as a bar chart."


def test_substituted_values_are_never_rescanned():
    """BND-20: a value that looks like a placeholder stays literal text."""
    prompt = _prompt(
        _user("{{a}} and {{b}}"),
        arguments=[PromptArgument(name="a"), PromptArgument(name="b")],
    )
    assert prompt.render({"a": "{{b}}", "b": "B"})[0].text == "{{b}} and B"


def test_render_leaves_resource_messages_alone():
    """BND-20"""
    embed = PromptMessage(role=PromptRole.USER, resource="guides/style")
    assert _prompt(embed).render({})[0] == embed


def test_missing_arguments_names_required_ones_in_order():
    """BND-21"""
    listing = PromptListing(
        name="chart",
        arguments=[
            PromptArgument(name="b", required=True),
            PromptArgument(name="opt"),
            PromptArgument(name="a", required=True),
        ],
    )
    assert listing.missing_arguments({"opt": "x"}) == ["b", "a"]
    assert listing.missing_arguments({"a": "1", "b": "2"}) == []


def test_check_references_rejects_undeclared_placeholders():
    """BND-20: a write naming an undeclared argument is rejected, naming it."""
    prompt = _prompt(_user("{{known}} {{unknown}}"), arguments=[PromptArgument(name="known")])
    with pytest.raises(BundleContentRejected, match="unknown"):
        prompt.check_references(set())


def test_check_references_rejects_unknown_resources():
    """BND-20: an embed must name a resource of the same bundle."""
    prompt = _prompt(PromptMessage(role=PromptRole.USER, resource="guides/style"))
    with pytest.raises(BundleContentRejected, match="guides/style"):
        prompt.check_references({"other"})
    prompt.check_references({"guides/style"})


def test_completions_are_case_insensitive_prefix_matches_in_order():
    """BND-22"""
    argument = PromptArgument(name="kind", values=["Bar", "bubble", "line", "BOX"])
    assert argument.completions("b") == ["Bar", "bubble", "BOX"]
    assert argument.completions("") == ["Bar", "bubble", "line", "BOX"]
    assert PromptArgument(name="free").completions("x") == []


def test_resource_size_is_measured_in_utf8_bytes():
    """BND-33: the size is derived from the content, never supplied."""
    resource = BundleResource(bundle_id=BUNDLE_ID, name="r", content="äb", size_bytes=999)
    assert resource.size_bytes == 3
    assert resource.mime_type is ResourceMimeType.MARKDOWN


def test_resource_uri_carries_no_bundle_name():
    """BND-24"""
    assert bundle_resource_uri("guides/style") == "bundle://resources/guides/style"
    assert bundle_resource_name("bundle://resources/guides/style") == "guides/style"
    assert bundle_resource_name("bundle://resources/") is None
    assert bundle_resource_name("bundle://other/x") is None
    assert is_bundle_uri("bundle://other/x") and not is_bundle_uri("res://x")


@pytest.mark.parametrize(
    ("limits", "prompts_after", "text", "match"),
    [
        (BundleContentLimits(max_prompts=2), 3, "x", "at most 2 prompts"),
        (BundleContentLimits(max_prompt_text_bytes=4), 1, "12345", "a prompt holds at most"),
    ],
)
def test_prompt_limits_name_themselves(limits, prompts_after, text, match):
    """BND-33: a write over a limit is refused with a message naming the limit."""
    with pytest.raises(BundleContentRejected, match=match):
        limits.check_prompt(_prompt(_user(text)), prompts_after=prompts_after)


def test_prompt_text_limit_is_64_kib_by_default():
    """BND-33: nothing is truncated; one byte over is refused."""
    limits = BundleContentLimits()
    limits.check_prompt(_prompt(_user("x" * 64 * 1024)), prompts_after=1)
    with pytest.raises(BundleContentRejected, match="64 KiB"):
        limits.check_prompt(_prompt(_user("x" * (64 * 1024 + 1))), prompts_after=1)


def test_resource_limits_name_themselves():
    """BND-33: per resource, per bundle count, and per bundle total."""
    limits = BundleContentLimits()
    big = BundleResource(bundle_id=BUNDLE_ID, name="r", content="x" * (256 * 1024 + 1))
    with pytest.raises(BundleContentRejected, match="256 KiB"):
        limits.check_resource(big, resources_after=1, bundle_bytes_after=big.size_bytes)
    small = BundleResource(bundle_id=BUNDLE_ID, name="r", content="x")
    with pytest.raises(BundleContentRejected, match="200 resources"):
        limits.check_resource(small, resources_after=201, bundle_bytes_after=1)
    with pytest.raises(BundleContentRejected, match="4 MiB"):
        limits.check_resource(small, resources_after=2, bundle_bytes_after=4 * 1024 * 1024 + 1)


def _view(**content) -> BundleView:
    bundle = Bundle(name="b")
    endpoint = Endpoint(name="e", bundle_id=bundle.id)
    return BundleView(endpoint=endpoint, bundle=bundle, servers={}, tools=[], **content)


def test_bundle_without_members_advertises_its_own_content():
    """BND-27: no member server at all, yet prompts, resources and completions are served."""
    caps = aggregate_capabilities(
        _view(
            prompts=[PromptListing(name="p", arguments=[PromptArgument(name="k", values=["a"])])],
            resources=[ResourceListing(name="r")],
        ),
        member_notifications=False,
    ).model_dump()
    assert caps["prompts"] == {"listChanged": True}
    assert caps["resources"] == {"listChanged": True}
    assert caps["completions"] == {}


def test_completions_not_advertised_without_suggested_values():
    """BND-27"""
    caps = aggregate_capabilities(
        _view(prompts=[PromptListing(name="p")]), member_notifications=False
    ).model_dump()
    assert "prompts" in caps and "completions" not in caps and "resources" not in caps
