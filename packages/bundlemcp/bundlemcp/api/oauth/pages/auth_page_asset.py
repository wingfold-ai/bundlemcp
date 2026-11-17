"""A file from the operator's asset directory, and the types that may be served."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

AUTH_PAGE_ASSETS_PATH = "/auth-pages/assets"
"""Where the operator's page assets are served; ``asset_url`` builds URLs under it."""

AUTH_PAGE_ASSET_TYPES: dict[str, str] = {
    ".css": "text/css; charset=utf-8",
    ".woff2": "font/woff2",
    ".woff": "font/woff",
    ".ttf": "font/ttf",
    ".otf": "font/otf",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".avif": "image/avif",
    ".ico": "image/x-icon",
}
"""The only extensions served, each with its content type; anything else is not found."""

AUTH_PAGE_ASSET_HEADERS: dict[str, str] = {
    "Cache-Control": "public, max-age=3600",
    "X-Content-Type-Options": "nosniff",
    # matters only when a file is opened on its own: an SVG then runs no script
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox",
}
"""Headers every served asset carries."""


class AuthPageAsset(BaseModel):
    """A file inside the asset directory that may be served, and how."""

    model_config = ConfigDict(frozen=True)

    path: Path = Field(description="The resolved file, known to lie inside the asset directory")
    media_type: str = Field(description="Content type sent with it, from its extension")
