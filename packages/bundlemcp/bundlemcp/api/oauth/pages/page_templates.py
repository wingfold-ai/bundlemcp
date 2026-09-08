"""The Jinja environment the gateway-rendered auth pages share."""

from jinja2 import Environment, PackageLoader, select_autoescape

PAGE_TEMPLATES = Environment(
    loader=PackageLoader("bundlemcp.api.oauth.pages", "templates"),
    autoescape=select_autoescape(["html"]),
)
