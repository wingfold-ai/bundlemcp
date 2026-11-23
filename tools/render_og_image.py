#!/usr/bin/env python3
"""Render the documentation site's link-preview image.

    uv run --no-project --with playwright tools/render_og_image.py

Opens docs/.vitepress/og-image/og.html in a headless Chromium at 1200x630 and
writes the screenshot to docs/public/og-image.png, the image every page's
Open Graph and Twitter card tags point to. Run it by hand after changing the
HTML or the logo files it uses; the docs build only serves the committed PNG.
The page loads its fonts from Google Fonts, so rendering needs network access.
"""

import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/.vitepress/og-image/og.html"
TARGET = ROOT / "docs/public/og-image.png"
WIDTH, HEIGHT = 1200, 630


async def render() -> None:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page(viewport={"width": WIDTH, "height": HEIGHT})
        await page.goto(SOURCE.as_uri(), wait_until="networkidle")
        await page.evaluate("document.fonts.ready")
        await page.screenshot(path=str(TARGET))
        await browser.close()


def main() -> int:
    asyncio.run(render())
    sys.stderr.write(f"Wrote {TARGET.relative_to(ROOT)} ({WIDTH}x{HEIGHT}).\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
