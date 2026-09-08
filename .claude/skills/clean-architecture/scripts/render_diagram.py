#!/usr/bin/env python3
"""Render a Clean Architecture concentric-rings diagram as SVG.

Usage:
    python render_diagram.py layers.json -o architecture.svg

Input schema: see references/diagram.md. Stdlib only.

Rings (centre outward): domain (circle) -> application (ring)
-> api (top half) + infrastructure (bottom half) -> composition root (thin band, optional).
Modules are drawn as rounded boxes inside their ring. Violations are red dashed arrows.
"""
import argparse
import json
import math
import sys
from xml.sax.saxutils import escape

COLORS = {
    "domain": ("#F4D8B8", "#B76E2A"),
    "application": ("#FBE7C6", "#C8933A"),
    "api": ("#DCE8F5", "#4A6FA5"),
    "infrastructure": ("#DDEFE3", "#3F8A5C"),
    "composition_root": ("#EEEEEE", "#777777"),
}
VIOLATION = "#C0392B"
FONT = "Inter, 'Helvetica Neue', Arial, sans-serif"

BOX_H = 34
ITEM_H = 14
BOX_PAD_X = 14
GAP = 22          # gap between boxes along a ring
RING_PAD = 26     # radial padding inside a ring around the boxes
LABEL_BAND = 22   # room near the outer edge of a ring for the ring label
MIN_DOMAIN_R = 120
MIN_RING_W = 110
ROOT_BAND = 34


# ---------- helpers ----------

def norm_module(m):
    if isinstance(m, str):
        return {"name": m, "items": []}
    return {"name": m.get("name", "?"), "items": list(m.get("items", []))[:3]}


def text_w(s, size):
    """Rough text width estimate (px)."""
    return len(s) * size * 0.58


def box_size(mod):
    w = text_w(mod["name"], 13)
    for it in mod["items"]:
        w = max(w, text_w(it, 10.5))
    w = max(72, w + 2 * BOX_PAD_X)
    h = BOX_H + ITEM_H * len(mod["items"])
    return w, h


def polar(cx, cy, r, deg):
    a = math.radians(deg)
    return cx + r * math.cos(a), cy + r * math.sin(a)


def ring_width_for(mods, inner_r, arc_frac):
    """Width a ring needs so that boxes fit along `arc_frac` of the circumference."""
    if not mods:
        return MIN_RING_W
    sizes = [box_size(m) for m in mods]
    max_h = max(h for _, h in sizes)
    needed_len = sum(w for w, _ in sizes) + GAP * len(sizes)
    base_w = max(MIN_RING_W, max_h + 2 * RING_PAD + LABEL_BAND)
    # mid radius of the box band = inner + RING_PAD + max_h/2
    mid = inner_r + RING_PAD + max_h / 2
    if 2 * math.pi * mid * arc_frac < needed_len:
        mid = needed_len / (2 * math.pi * arc_frac)
        base_w = max(base_w, (mid - inner_r) * 2 - max_h + max_h + LABEL_BAND)
        base_w = max(base_w, (mid - inner_r) + max_h / 2 + RING_PAD + LABEL_BAND)
    return base_w


def domain_radius(mods):
    if not mods:
        return MIN_DOMAIN_R
    sizes = [box_size(m) for m in mods]
    n = len(mods)
    cols = math.ceil(math.sqrt(n))
    rows = math.ceil(n / cols)
    max_w = max(w for w, _ in sizes)
    max_h = max(h for _, h in sizes)
    grid_w = cols * max_w + (cols - 1) * 12
    grid_h = rows * max_h + (rows - 1) * 12 + 30  # label room
    half_diag = math.sqrt(grid_w ** 2 + grid_h ** 2) / 2
    return max(MIN_DOMAIN_R, half_diag + 18)


# ---------- SVG bits ----------

def svg_box(x, y, mod, layer, out, positions, key):
    w, h = box_size(mod)
    fill, stroke = COLORS[layer]
    bx, by = x - w / 2, y - h / 2
    out.append(f'<rect x="{bx:.1f}" y="{by:.1f}" width="{w:.1f}" height="{h:.1f}" rx="8" '
               f'fill="#FFFFFF" fill-opacity="0.92" stroke="{stroke}" stroke-width="1.2"/>')
    ty = by + 21
    out.append(f'<text x="{x:.1f}" y="{ty:.1f}" text-anchor="middle" font-family="{FONT}" '
               f'font-size="13" font-weight="600" fill="#222">{escape(mod["name"])}</text>')
    for i, it in enumerate(mod["items"]):
        out.append(f'<text x="{x:.1f}" y="{ty + 15 + i * ITEM_H:.1f}" text-anchor="middle" '
                   f'font-family="{FONT}" font-size="10.5" fill="#555">{escape(it)}</text>')
    positions[key] = (x, y, w, h)


def ring_label(out, cx, cy, r, text, color, top=True, pid=""):
    # arc text along the ring near radius r; top: sweep over the top, else bottom
    if top:
        x1, y1 = cx - r, cy
        x2, y2 = cx + r, cy
        d = f"M {x1:.1f} {y1:.1f} A {r:.1f} {r:.1f} 0 0 1 {x2:.1f} {y2:.1f}"
    else:
        x1, y1 = cx - r, cy
        x2, y2 = cx + r, cy
        d = f"M {x1:.1f} {y1:.1f} A {r:.1f} {r:.1f} 0 0 0 {x2:.1f} {y2:.1f}"
    out.append(f'<defs><path id="{pid}" d="{d}"/></defs>')
    out.append(f'<text font-family="{FONT}" font-size="13" font-weight="700" letter-spacing="2" fill="{color}">'
               f'<textPath href="#{pid}" startOffset="50%" text-anchor="middle">{escape(text)}</textPath></text>')


def arrow_between(out, a, b, label, cx, cy, r_out):
    """Curved red dashed arrow between two module boxes, bulging away from the centre
    so it doesn't cut through inner rings."""
    (ax, ay, aw, ah), (bx, by, bw, bh) = a, b
    mx, my = (ax + bx) / 2, (ay + by) / 2
    vx, vy = mx - cx, my - cy
    vlen = math.hypot(vx, vy) or 1
    ux, uy = vx / vlen, vy / vlen
    # push control point outward; the closer the chord passes to the centre, the more it bulges
    chord = math.hypot(bx - ax, by - ay)
    bulge = max(60, chord * 0.45)
    ctrl_r = max(vlen + bulge, min(r_out + 20, vlen + bulge))
    qx, qy = cx + ux * ctrl_r, cy + uy * ctrl_r
    # trim start/end away from box centres along the initial/final tangents
    def trim(px, py, tx, ty, w, h):
        dx, dy = tx - px, ty - py
        d = math.hypot(dx, dy) or 1
        k = min(w, h) / 2 + 6
        return px + dx / d * k, py + dy / d * k
    x1, y1 = trim(ax, ay, qx, qy, aw, ah)
    x2, y2 = trim(bx, by, qx, qy, bw, bh)
    out.append(f'<path d="M {x1:.1f} {y1:.1f} Q {qx:.1f} {qy:.1f} {x2:.1f} {y2:.1f}" fill="none" '
               f'stroke="{VIOLATION}" stroke-width="2" stroke-dasharray="6 4" marker-end="url(#viol-arrow)"/>')
    if label:
        # point on the quadratic curve at t=0.5
        lx = 0.25 * x1 + 0.5 * qx + 0.25 * x2
        ly = 0.25 * y1 + 0.5 * qy + 0.25 * y2
        tw = text_w(label, 10) + 8
        out.append(f'<rect x="{lx - tw/2:.1f}" y="{ly - 9:.1f}" width="{tw:.1f}" height="16" rx="3" fill="#FFF" fill-opacity="0.9"/>')
        out.append(f'<text x="{lx:.1f}" y="{ly + 3:.1f}" text-anchor="middle" font-family="{FONT}" '
                   f'font-size="10" fill="{VIOLATION}">{escape(label)}</text>')


# ---------- main render ----------

def render(spec):
    layers = {k: [norm_module(m) for m in spec.get("layers", {}).get(k, [])]
              for k in ("domain", "application", "api", "infrastructure")}
    root = spec.get("composition_root")
    title = spec.get("title", "")
    subtitle = spec.get("subtitle", "")
    legend = spec.get("legend", True)
    violations = spec.get("violations", [])

    r_dom = domain_radius(layers["domain"])
    w_app = ring_width_for(layers["application"], r_dom, 1.0)
    r_app = r_dom + w_app
    w_out = max(ring_width_for(layers["api"], r_app, 0.5),
                ring_width_for(layers["infrastructure"], r_app, 0.5))
    r_out = r_app + w_out
    r_root = r_out + (ROOT_BAND if root else 0)

    margin = 50
    top_extra = 70 if (title or subtitle) else 20
    bottom_extra = 60 if legend else 20
    size = 2 * r_root + 2 * margin
    W = size
    H = size + top_extra + bottom_extra
    cx = W / 2
    cy = top_extra + margin + r_root

    out = []
    out.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:.0f} {H:.0f}" width="{W:.0f}" height="{H:.0f}">')
    out.append('<defs>'
               f'<marker id="viol-arrow" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto">'
               f'<path d="M0,0 L10,5 L0,10 z" fill="{VIOLATION}"/></marker>'
               '<marker id="in-arrow" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto">'
               '<path d="M0,0 L10,5 L0,10 z" fill="#333"/></marker>'
               '</defs>')
    out.append(f'<rect width="{W:.0f}" height="{H:.0f}" fill="#FFFFFF"/>')

    if title:
        out.append(f'<text x="{cx:.1f}" y="34" text-anchor="middle" font-family="{FONT}" font-size="20" font-weight="700" fill="#222">{escape(title)}</text>')
    if subtitle:
        out.append(f'<text x="{cx:.1f}" y="56" text-anchor="middle" font-family="{FONT}" font-size="13" fill="#666">{escape(subtitle)}</text>')

    # rings, outermost first
    if root:
        f, s = COLORS["composition_root"]
        out.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r_root:.1f}" fill="{f}" stroke="{s}" stroke-width="1"/>')
    # outer ring: api top, infra bottom
    fa, sa = COLORS["api"]
    fi, si = COLORS["infrastructure"]
    out.append(f'<path d="M {cx - r_out:.1f} {cy:.1f} A {r_out:.1f} {r_out:.1f} 0 0 1 {cx + r_out:.1f} {cy:.1f} Z" fill="{fa}" stroke="{sa}" stroke-width="1"/>')
    out.append(f'<path d="M {cx - r_out:.1f} {cy:.1f} A {r_out:.1f} {r_out:.1f} 0 0 0 {cx + r_out:.1f} {cy:.1f} Z" fill="{fi}" stroke="{si}" stroke-width="1"/>')
    fp, sp = COLORS["application"]
    out.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r_app:.1f}" fill="{fp}" stroke="{sp}" stroke-width="1"/>')
    fd, sd = COLORS["domain"]
    out.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r_dom:.1f}" fill="{fd}" stroke="{sd}" stroke-width="1.2"/>')
    # divider between api and infrastructure
    out.append(f'<line x1="{cx - r_out:.1f}" y1="{cy:.1f}" x2="{cx - r_app:.1f}" y2="{cy:.1f}" stroke="#888" stroke-width="1" stroke-dasharray="4 3"/>')
    out.append(f'<line x1="{cx + r_app:.1f}" y1="{cy:.1f}" x2="{cx + r_out:.1f}" y2="{cy:.1f}" stroke="#888" stroke-width="1" stroke-dasharray="4 3"/>')

    # ring labels
    ring_label(out, cx, cy, r_out - 12, "API", sa, top=True, pid="p-api")
    ring_label(out, cx, cy, r_out - 12, "INFRASTRUCTURE", si, top=False, pid="p-infra")
    ring_label(out, cx, cy, r_app - 12, "APPLICATION", sp, top=True, pid="p-app")
    out.append(f'<text x="{cx:.1f}" y="{cy - r_dom + 20:.1f}" text-anchor="middle" font-family="{FONT}" font-size="13" font-weight="700" letter-spacing="2" fill="{sd}">DOMAIN</text>')
    if root:
        fr, sr = COLORS["composition_root"]
        out.append(f'<text x="{cx:.1f}" y="{cy - r_root + 22:.1f}" text-anchor="middle" font-family="{FONT}" font-size="12" font-weight="600" letter-spacing="1" fill="{sr}">COMPOSITION ROOT · {escape(str(root))}</text>')

    positions = {}

    # domain grid
    dm = layers["domain"]
    if dm:
        n = len(dm)
        cols = math.ceil(math.sqrt(n))
        rows = math.ceil(n / cols)
        sizes = [box_size(m) for m in dm]
        mw = max(w for w, _ in sizes)
        mh = max(h for _, h in sizes)
        gw = cols * mw + (cols - 1) * 12
        gh = rows * mh + (rows - 1) * 12
        y0 = cy - gh / 2 + mh / 2 + 10
        for i, m in enumerate(dm):
            r_, c_ = divmod(i, cols)
            in_row = min(cols, n - r_ * cols)
            row_w = in_row * mw + (in_row - 1) * 12
            x = cx - row_w / 2 + mw / 2 + c_ * (mw + 12)
            y = y0 + r_ * (mh + 12)
            svg_box(x, y, m, "domain", out, positions, f"domain/{m['name']}")

    # application ring: full circle, avoid 12 o'clock (label sits there)
    am = layers["application"]
    if am:
        mh = max(box_size(m)[1] for m in am)
        mid = r_dom + RING_PAD + mh / 2 + (w_app - LABEL_BAND - mh - 2 * RING_PAD) / 2
        n = len(am)
        for i, m in enumerate(am):
            deg = -90 + 360 * (i + 0.5) / n
            x, y = polar(cx, cy, mid, deg)
            svg_box(x, y, m, "application", out, positions, f"application/{m['name']}")

    # outer ring halves
    for layer, start in (("api", 180), ("infrastructure", 0)):
        ms = layers[layer]
        if not ms:
            continue
        mh = max(box_size(m)[1] for m in ms)
        mid = r_app + RING_PAD + mh / 2 + (w_out - LABEL_BAND - mh - 2 * RING_PAD) / 2
        n = len(ms)
        for i, m in enumerate(ms):
            deg = start + 180 * (i + 0.5) / n
            x, y = polar(cx, cy, mid, deg)
            svg_box(x, y, m, layer, out, positions, f"{layer}/{m['name']}")

    # violations
    for v in violations:
        a, b = positions.get(v.get("from")), positions.get(v.get("to"))
        if not a or not b:
            print(f"warning: violation references unknown module: {v}", file=sys.stderr)
            continue
        arrow_between(out, a, b, v.get("label", ""), cx, cy, r_out)

    # legend
    if legend:
        ly = H - 28
        lx = margin
        out.append(f'<line x1="{lx:.1f}" y1="{ly:.1f}" x2="{lx + 46:.1f}" y2="{ly:.1f}" stroke="#333" stroke-width="2" marker-end="url(#in-arrow)"/>')
        out.append(f'<text x="{lx + 56:.1f}" y="{ly + 4:.1f}" font-family="{FONT}" font-size="12" fill="#333">'
                   'Dependencies point inward — outer rings may reference inner rings, never the reverse.</text>')
        if violations:
            out.append(f'<line x1="{W - margin - 260:.1f}" y1="{ly:.1f}" x2="{W - margin - 214:.1f}" y2="{ly:.1f}" stroke="{VIOLATION}" stroke-width="2" stroke-dasharray="6 4" marker-end="url(#viol-arrow)"/>')
            out.append(f'<text x="{W - margin - 204:.1f}" y="{ly + 4:.1f}" font-family="{FONT}" font-size="12" fill="{VIOLATION}">dependency-rule violation</text>')

    out.append('</svg>')
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec", help="JSON file describing layers/modules")
    ap.add_argument("-o", "--out", default="architecture.svg")
    args = ap.parse_args()
    with open(args.spec) as f:
        spec = json.load(f)
    svg = render(spec)
    with open(args.out, "w") as f:
        f.write(svg)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
