"""The operator's stylesheets, fonts and images for the auth pages."""

from fastapi import HTTPException
from fastapi.responses import FileResponse

from bundlemcp.api.http.controller import Controller
from bundlemcp.api.http.route import route
from bundlemcp.api.oauth.pages.auth_page_asset import AUTH_PAGE_ASSET_HEADERS, AUTH_PAGE_ASSETS_PATH
from bundlemcp.api.oauth.providers import AuthPagesProvider


class AuthPageAssetController(Controller):
    """Serves files from the operator's asset directory, read-only and unauthenticated.

    Mounted only when an asset directory is configured. Anything the lookup
    refuses (a directory, a hidden file, an unlisted type, a path leaving the
    directory) is answered as not found.
    """

    prefix = AUTH_PAGE_ASSETS_PATH
    tags = ("auth-pages",)
    include_in_schema = False

    @route.get("/{path:path}")
    async def asset(self, path: str, pages: AuthPagesProvider) -> FileResponse:
        found = pages.asset(path)
        if found is None:
            raise HTTPException(404, "Not Found")
        return FileResponse(
            found.path, media_type=found.media_type, headers=AUTH_PAGE_ASSET_HEADERS
        )
