"""Link previews for the documentation site: the shared image and the per-page tags (DOC-19)."""

import pathlib
import struct

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[4]
IMAGE = ROOT / "docs/public/og-image.png"
CONFIG = ROOT / "docs/.vitepress/config.ts"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def test_doc19_the_preview_image_is_1200_by_630():
    """DOC-19: the shared preview image is a PNG of exactly the size the tags announce."""
    header = IMAGE.read_bytes()[:24]
    assert header[:8] == PNG_SIGNATURE
    assert struct.unpack(">II", header[16:24]) == (1200, 630)


@pytest.mark.parametrize(
    "tag",
    [
        'property: "og:image", content: previewImage',
        'property: "og:image:width", content: "1200"',
        'property: "og:image:height", content: "630"',
        'property: "og:image:alt"',
        'name: "twitter:card", content: "summary_large_image"',
        'property: "og:title", content: title',
        'property: "og:description", content: description',
        'property: "og:url", content: pageUrl(pageData.relativePath)',
    ],
)
def test_doc19_every_page_gets_preview_tags(tag):
    """DOC-19: the site config declares each Open Graph and Twitter card tag: the image at the
    site's address, and the title, description and URL per page."""
    config = CONFIG.read_text()
    assert tag in config
    assert 'const previewImage = `${siteUrl}/og-image.png`' in config
