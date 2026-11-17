"""The gateway-rendered auth pages as one object: templates, headers and assets."""

from collections.abc import Callable
from pathlib import Path, PurePosixPath
from urllib.parse import quote

from jinja2 import Environment
from pydantic import BaseModel, ConfigDict, Field

from bundlemcp.api.oauth.pages.auth_page import AuthPage
from bundlemcp.api.oauth.pages.auth_page_asset import (
    AUTH_PAGE_ASSET_TYPES,
    AUTH_PAGE_ASSETS_PATH,
    AuthPageAsset,
)
from bundlemcp.api.oauth.pages.broken_auth_page import BrokenAuthPage
from bundlemcp.api.oauth.pages.page_headers import page_headers
from bundlemcp.api.oauth.pages.page_templates import page_templates
from bundlemcp.application.settings.settings import Settings


class AuthPages(BaseModel):
    """Renders the auth pages, with the headers they are served under and their assets.

    Built once at startup from the operator's settings; ``verify`` proves every
    page renders before the first request.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    templates: Environment = Field(
        description="Where the page templates load from: the operator's overrides, then the "
        "built-in templates"
    )
    template_dir: Path | None = Field(
        description="The operator's override directory; None renders the built-in pages only"
    )
    asset_dir: Path | None = Field(
        description="The resolved directory assets are served from; None when none is configured"
    )

    def render(self, page: AuthPage, **values: str) -> str:
        """The page's HTML, its values escaped."""
        return self.templates.get_template(page.value).render(**values)

    def headers(self, *, form_redirect_source: str | None = None) -> dict[str, str]:
        """The hardening headers for a page; see ``page_headers``."""
        return page_headers(
            form_redirect_source=form_redirect_source, assets=self.asset_dir is not None
        )

    def asset(self, path: str) -> AuthPageAsset | None:
        """The servable file at ``path`` under the asset directory, or None.

        None, before any disk access, for a path that is absolute, holds a
        backslash or NUL, has an empty, ``.``, ``..`` or hidden segment, or an
        extension that is not served; after resolving symbolic links, None
        unless the result is a regular file inside the asset directory.
        """
        if self.asset_dir is None or "\\" in path or "\x00" in path:
            return None
        segments = path.split("/")
        if any(not segment or segment.startswith(".") for segment in segments):
            return None
        media_type = AUTH_PAGE_ASSET_TYPES.get(PurePosixPath(path).suffix.lower())
        if media_type is None:
            return None
        candidate = self.asset_dir.joinpath(*segments).resolve()
        if not candidate.is_relative_to(self.asset_dir) or not candidate.is_file():
            return None
        return AuthPageAsset(path=candidate, media_type=media_type)

    def verify(self) -> None:
        """Load, compile and render every page with its sample values.

        Raises ``BrokenAuthPage`` naming the first page that fails, and the
        file it came from.
        """
        for page in AuthPage:
            try:
                self.render(page, **page.sample_values)
            except Exception as exc:
                raise BrokenAuthPage(
                    f"auth page {page.value} ({self._origin(page)}) failed its startup check: "
                    f"{type(exc).__name__}: {exc}"
                ) from exc

    def _origin(self, page: AuthPage) -> str:
        if self.template_dir is not None and (self.template_dir / page.value).is_file():
            return str(self.template_dir / page.value)
        return "built-in template"


def auth_pages(settings: Settings) -> AuthPages:
    """The auth pages as the settings configure them; not yet verified."""
    asset_dir = settings.auth_pages_asset_dir
    resolved_assets = asset_dir.resolve() if asset_dir is not None else None
    return AuthPages(
        templates=page_templates(
            settings.auth_pages_template_dir, asset_url=_asset_url_builder(resolved_assets)
        ),
        template_dir=settings.auth_pages_template_dir,
        asset_dir=resolved_assets,
    )


def _asset_url_builder(asset_dir: Path | None) -> Callable[[str], str]:
    def asset_url(path: str) -> str:
        """The URL of a file in the operator's asset directory, e.g. ``asset_url('logo.svg')``."""
        if asset_dir is None:
            raise ValueError(
                "asset_url() needs an asset directory: set BUNDLEMCP_AUTH_PAGES_ASSET_DIR"
            )
        segments = path.split("/")
        if any(segment in ("", ".", "..") for segment in segments):
            raise ValueError(
                f"asset_url() takes a relative path inside the asset directory, not {path!r}"
            )
        return f"{AUTH_PAGE_ASSETS_PATH}/{'/'.join(quote(s, safe='') for s in segments)}"

    return asset_url
