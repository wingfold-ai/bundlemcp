# Architecture diagram spec

The canonical picture: concentric rings, dependencies point inward.

```
        ┌──────────── composition root (thin outer band) ────────────┐
        │  ┌──────────────────  api  (top half)  ──────────────────┐ │
        │  │      ┌──────────  application  ──────────┐            │ │
        │  │      │        ┌──── domain ────┐         │            │ │
        │  │      │        │  orders  pricing│         │            │ │
        │  │      │        │    customers   │         │            │ │
        │  │      │        └────────────────┘         │            │ │
        │  │      │   orders   ports   customers      │            │ │
        │  │      └───────────────────────────────────┘            │ │
        │  └──────────── infrastructure (bottom half) ─────────────┘ │
        └────────────────────────────────────────────────────────────┘
```

Rings from the centre outward:
1. **domain** — filled circle, warmest colour.
2. **application** — full ring.
3. **api** (top half) and **infrastructure** (bottom half) — one ring split in two sectors. They share a ring because both depend only inward and neither depends on the other. Do *not* draw infrastructure as a ring inside api; that would say api depends on infrastructure.
4. **composition root** — thin outermost band with a single label (e.g. `main.py`). Optional.

Inside each ring, the project's **modules** are drawn as rounded boxes: the sub-folders of the layer folder (`api/http`, `infrastructure/postgres`, `application/orders`). Each box has the module name and optionally up to three notable items in smaller text (`OrderRepository`, `UnitOfWork`). Use classes as modules only if the layer has no sub-folders.

Legend (always include): *Dependencies point inward — outer rings may reference inner rings, never the reverse.*

Optional overlays:
- **Violation edges** — red dashed arrows from module to module for illegal dependencies found in an audit (`api/http → infrastructure/postgres`). Used in the "current state" diagram.
- **Title / subtitle** — project name, "current state" vs "target state", date.

---

## Rendering

```
python scripts/render_diagram.py layers.json -o architecture.svg
```

Stdlib-only Python; produces a standalone SVG (fixed colours, no CSS variables, so it opens anywhere). Convert to PNG with any SVG tool if needed (`rsvg-convert`, `cairosvg`, Inkscape).

### Input JSON

```json
{
  "title": "orders-service",
  "subtitle": "target state",
  "layers": {
    "domain": [
      "orders",
      {"name": "pricing", "items": ["PricingService"]},
      "customers"
    ],
    "application": [
      {"name": "ports", "items": ["OrderRepository", "PaymentGateway", "UnitOfWork"]},
      {"name": "orders", "items": ["PlaceOrder", "CancelOrder"]},
      "customers"
    ],
    "infrastructure": [
      {"name": "postgres", "items": ["PostgresOrderRepository", "SqlUnitOfWork"]},
      {"name": "stripe", "items": ["StripePaymentGateway"]},
      {"name": "memory", "items": ["InMemoryOrderRepository"]}
    ],
    "api": [
      {"name": "http", "items": ["orders router", "customers router"]},
      "cli"
    ]
  },
  "composition_root": "main.py",
  "violations": [
    {"from": "api/http", "to": "infrastructure/postgres", "label": "imports SqlOrderRepository"}
  ],
  "legend": true
}
```

- `layers.<layer>` — list of modules. A module is a string or `{"name", "items"}`. Keep to ≤ 8 modules per layer and ≤ 3 items per module; beyond that the ring gets crowded — group by folder, or make a second diagram per bounded context.
- `composition_root` — string or `null` to omit the band.
- `violations` — module references as `layer/module`. Unknown references are skipped with a warning.
- `legend` — default `true`.

### How to build the JSON from a real project

1. From the layer mapping (evaluation.md §2), list the immediate sub-folders of each layer folder. Those are the modules.
2. For each module pick 1–3 items worth naming: the port interfaces in `ports/`, the concrete adapter classes in `infrastructure/*`, the use cases in `application/*`, the routers in `api/*`.
3. For a current-state diagram of a messy project, keep the *mapped* layer as the ring even if the folder isn't named that way, and set the module name to the real folder (`services` in the application ring, `models` in the domain ring). Add violations from `scan_imports.py` output — its `edges` entries carry `from_module`/`to_module` in the right format.
4. For a target-state diagram, use the folder skeleton you propose.

### Layout rules (for hand-writing SVG when the script can't run)

- Canvas ~ 900×900 (grows with content). Centre `(cx, cy)`.
- Domain radius ≥ 120; each ring width ≥ 110; composition root band 34.
- Module boxes: height 34 (+14 per item line), width from text length, corner radius 8, 1px border in the ring's darker shade, white fill at ~90% opacity.
- Domain modules: grid inside the circle, label "DOMAIN" at the top of the circle.
- Application modules: evenly spaced on the ring's mid-radius, angles offset so none sits at 12 o'clock; layer label on a text path near the outer edge.
- API modules: spread across the top semicircle (angles 180°→360°); infrastructure across the bottom (0°→180°); a horizontal divider line at the ring's left and right edges.
- Colours: domain `#F4D8B8`/`#B76E2A`, application `#FBE7C6`/`#C8933A`, api `#DCE8F5`/`#4A6FA5`, infrastructure `#DDEFE3`/`#3F8A5C`, composition root `#EEEEEE`/`#777777`, violations `#C0392B` dashed with arrowhead.
- Inward-arrow marker at the top-left quadrant with the legend text below the diagram.
