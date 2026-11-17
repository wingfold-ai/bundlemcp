"""The Jinja environment the gateway-rendered auth pages are loaded from."""

from collections.abc import Callable
from pathlib import Path

from jinja2 import (
    BaseLoader,
    ChoiceLoader,
    Environment,
    FileSystemLoader,
    PackageLoader,
    StrictUndefined,
    select_autoescape,
)


def page_templates(override_dir: Path | None, *, asset_url: Callable[[str], str]) -> Environment:
    """The environment for the auth pages, an operator's directory searched first.

    A template found in ``override_dir`` replaces the built-in one of the same
    name; every other name falls through to the templates shipped in the
    package. Output is HTML-escaped either way, and a variable the page is not
    given is an error rather than an empty string. ``asset_url`` is offered to
    every template as a global function.
    """
    built_in = PackageLoader("bundlemcp.api.oauth.pages", "templates")
    loader: BaseLoader = built_in
    if override_dir is not None:
        loader = ChoiceLoader([FileSystemLoader(override_dir), built_in])
    environment = Environment(
        loader=loader,
        autoescape=select_autoescape(["html"]),
        undefined=StrictUndefined,
    )
    environment.globals["asset_url"] = asset_url
    return environment
