"""Render the wordmark in logo-text.html as path-based SVGs.

The HTML needs a browser, a script and the Roboto web font; GitHub's README
renderer and an ``<img>`` tag get none of those. This script traces the same
composition with the real Roboto outlines so the result renders identically
everywhere: the bold "bundle" (with the mirrored "d" as the "b", slits cut
out), the light "mcp", and the subtitle stretched to the ink width of the
title.

Run from the repository root::

    uv run --with fonttools python docs/brand/build_logo_text.py

Fonts are fetched into docs/brand/.fonts/ on first use.
"""

from __future__ import annotations

import re
import sys
import urllib.request
from pathlib import Path

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

HERE = Path(__file__).parent
PUBLIC = HERE.parent / "public"
FONTS = HERE / ".fonts"
UA = "Mozilla/5.0 (Windows NT 6.1; WOW64; rv:27.0) Gecko/20100101 Firefox/27.0"

# From logo-text.html
BG = "#242e30"
TITLE_DARK = "#94cdd2"
SUB_DARK = "#8b8d8e"
# The same hue, darkened for a light page
TITLE_LIGHT = "#2c7f86"
SUB_LIGHT = "#6b6e70"

T = 160.0  # title font size, px
SUB = 0.31 * T  # subtitle font size
BOLD_TRACK = -0.02 * T  # letter-spacing on the bold span
SLIT_H = 0.53 * T  # bowl height the slit overlay spans


def font(weight: int) -> TTFont:
    FONTS.mkdir(exist_ok=True)
    path = FONTS / f"roboto-{weight}.woff"
    if not path.exists():
        css = urllib.request.urlopen(
            urllib.request.Request(
                f"https://fonts.googleapis.com/css2?family=Roboto:wght@{weight}&display=swap",
                headers={"User-Agent": UA},
            )
        ).read().decode()
        url = re.search(r"url\((https://[^)]+)\)", css).group(1)
        path.write_bytes(urllib.request.urlopen(url).read())
    return TTFont(path)


class Face:
    def __init__(self, weight: int) -> None:
        self.tt = font(weight)
        self.glyphs = self.tt.getGlyphSet()
        self.cmap = self.tt.getBestCmap()
        self.scale = 1.0 / self.tt["head"].unitsPerEm
        self.ascent = self.tt["hhea"].ascent * self.scale
        self.descent = -self.tt["hhea"].descent * self.scale

    def name(self, ch: str) -> str:
        return self.cmap[ord(ch)]

    def advance(self, ch: str, size: float) -> float:
        return self.tt["hmtx"][self.name(ch)][0] * self.scale * size

    def ink(self, ch: str, size: float) -> tuple[float, float]:
        pen = BoundsPen(self.glyphs)
        self.glyphs[self.name(ch)].draw(pen)
        xmin, _, xmax, _ = pen.bounds
        return xmin * self.scale * size, xmax * self.scale * size

    def path(self, ch: str, size: float, x: float, y: float, mirror: bool = False) -> str:
        """SVG path data for one glyph with its origin at (x, y), y down."""
        s = self.scale * size
        sx = -s if mirror else s
        dx = x + (self.advance(ch, size) if mirror else 0.0)
        pen = SVGPathPen(self.glyphs, ntos=lambda v: f"{v:.2f}")
        self.glyphs[self.name(ch)].draw(TransformPen(pen, (sx, 0, 0, -s, dx, y)))
        return pen.getCommands()


def wordmark(title_color: str, sub_color: str, with_subtitle: bool) -> tuple[str, float, float, float]:
    """Return (svg fragment, width, height, baseline-of-title) with the origin at
    the title's line-box top-left, as the HTML lays it out."""
    bold, light, regular = Face(700), Face(300), Face(400)

    # Vertical layout: line-height 1 puts the baseline at half-leading + ascent
    content = bold.ascent + bold.descent
    baseline = (1.0 - content) / 2 * T + bold.ascent * T
    line_bottom = T

    paths: list[str] = []
    x = 0.0
    # the "b": the bold "d" mirrored about its advance box, slits cut out later
    b_adv = bold.advance("d", T)
    b_path = bold.path("d", T, x, baseline, mirror=True)
    d_ink = bold.ink("d", T)
    ink_start = x + (b_adv - d_ink[1])  # d's right bearing becomes b's left bearing
    slit_x, slit_w = x, b_adv + BOLD_TRACK  # the glyph box the overlay spans
    x += b_adv + BOLD_TRACK
    for ch in "undle":
        paths.append(bold.path(ch, T, x, baseline))
        x += bold.advance(ch, T) + BOLD_TRACK
    for ch in "mcp":
        paths.append(light.path(ch, T, x, baseline))
        x += light.advance(ch, T)
    width = x
    p_ink = light.ink("p", T)
    ink_end = width - (light.advance("p", T) - p_ink[1])  # p's right bearing

    sx, sy = slit_w / 100.0, SLIT_H / 53.0
    mask = (
        f'<mask id="b-slits" maskUnits="userSpaceOnUse" x="0" y="0" width="{width:.1f}" height="{T:.1f}">'
        f'<rect width="{width:.1f}" height="{T:.1f}" fill="#fff"/>'
        f'<g transform="translate({slit_x:.2f},{baseline - SLIT_H:.2f}) scale({sx:.4f},{sy:.4f})" '
        f'fill="none" stroke="#000" stroke-width="4.5">'
        '<path d="M-2 12 Q50 19 102 12"/><path d="M-2 25 Q50 32 102 25"/><path d="M-2 38 Q50 45 102 38"/>'
        "</g></mask>"
    )
    out = [
        "<defs>" + mask + "</defs>",
        f'<path d="{b_path}" fill="{title_color}" mask="url(#b-slits)"/>',
        f'<path d="{" ".join(paths)}" fill="{title_color}"/>',
    ]
    height = line_bottom
    if with_subtitle:
        text = "unified mcp server bundler"
        # margin-top 0.06em of the wrapper's own font-size (T), text at y=0.95em of SUB
        sub_baseline = line_bottom + 0.06 * T + 0.95 * SUB
        height = line_bottom + 0.06 * T + 1.25 * SUB
        u_ink, r_ink = regular.ink("u", SUB), regular.ink("r", SUB)
        start = ink_start - u_ink[0]
        end = ink_end - (r_ink[1] - regular.advance("r", SUB))  # pen position after the final r
        natural = sum(regular.advance(c, SUB) for c in text)
        extra = (end - start - natural) / (len(text) - 1)
        sub_paths, sx_ = [], start
        for ch in text:
            if ch != " ":
                sub_paths.append(regular.path(ch, SUB, sx_, sub_baseline))
            sx_ += regular.advance(ch, SUB) + extra
        out.append(f'<path d="{" ".join(sub_paths)}" fill="{sub_color}"/>')
    return "\n".join(out), width, height, baseline


def mark_fragment() -> str:
    svg = (PUBLIC / "logo-mark.svg").read_text()
    body = svg[svg.index(">") + 1 : svg.rindex("</svg>")]
    return re.sub(r"<title>.*?</title>", "", body, flags=re.S).strip()


MARK_W, MARK_H = 1120.0, 1020.0


def svg(width: float, height: float, body: str, label: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.1f} {height:.1f}" '
        f'role="img" aria-label="{label}">\n<title>{label}</title>\n{body}\n</svg>\n'
    )


def write(name: str, content: str) -> None:
    (PUBLIC / name).write_text(content)
    print(f"wrote public/{name}")


def main() -> None:
    # 1. The wordmark with subtitle, transparent, for dark and light pages.
    for suffix, tc, sc in (("dark", TITLE_DARK, SUB_DARK), ("light", TITLE_LIGHT, SUB_LIGHT)):
        body, w, h, _ = wordmark(tc, sc, True)
        pad = 8.0
        write(
            f"wordmark-{suffix}.svg",
            svg(w + 2 * pad, h + pad, f'<g transform="translate({pad},0)">{body}</g>',
                "bundlemcp: unified mcp server bundler"),
        )

    # 2. The lockup for a navigation bar: mark + title, no subtitle.
    for suffix, tc, sc in (("dark", TITLE_DARK, SUB_DARK), ("light", TITLE_LIGHT, SUB_LIGHT)):
        body, w, h, baseline = wordmark(tc, sc, False)
        # the mark stands well above and below the text, centred on the ascender box
        mark_h = 2.1 * T
        mark_w = mark_h * MARK_W / MARK_H
        gap = 0.14 * T
        text_mid = baseline - 0.36 * T  # midpoint between baseline and ascender top
        top = text_mid - mark_h / 2
        shift = max(0.0, -top)  # keep the mark inside the canvas
        total_w = mark_w + gap + w
        total_h = max(h, top + mark_h) + shift
        write(
            f"lockup-{suffix}.svg",
            svg(
                total_w, total_h,
                f'<g transform="translate(0,{top + shift:.2f}) scale({mark_h / MARK_H:.5f})">{mark_fragment()}</g>\n'
                f'<g transform="translate({mark_w + gap:.2f},{shift:.2f})">{body}</g>',
                "bundlemcp",
            ),
        )

    # 3. The banner: dark rounded background, mark + wordmark + subtitle.
    body, w, h, baseline = wordmark(TITLE_DARK, SUB_DARK, True)
    mark_h = h * 1.7  # the mark dominates; the wordmark sits centred beside it
    mark_w = mark_h * MARK_W / MARK_H
    gap, pad_x, pad_y = 0.3 * T, 0.45 * T, 0.25 * T
    total_w = pad_x + mark_w + gap + w + pad_x
    total_h = mark_h + 2 * pad_y
    rx = total_h * 96 / 1020  # the corner radius ratio of logo.svg
    write(
        "banner.svg",
        svg(
            total_w, total_h,
            f'<rect width="{total_w:.1f}" height="{total_h:.1f}" rx="{rx:.1f}" fill="{BG}"/>\n'
            f'<g transform="translate({pad_x:.2f},{pad_y:.2f}) scale({mark_h / MARK_H:.5f})">{mark_fragment()}</g>\n'
            f'<g transform="translate({pad_x + mark_w + gap:.2f},{pad_y + (mark_h - h) / 2:.2f})">{body}</g>',
            "bundlemcp: unified mcp server bundler",
        ),
    )


if __name__ == "__main__":
    sys.exit(main())
