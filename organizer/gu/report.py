"""Top-down SVG diagram of the layout and sections."""

from __future__ import annotations

import math
from html import escape

from .layout import Resolved
from .seams import Section

SECTION_COLOURS = ["#d9560a", "#2f6db5", "#2f7d4f", "#8a4fb3", "#c2a20a", "#b8336a", "#3a8f8f", "#6b6b6b"]


def layout_svg(res: Resolved, sections: list[Section]) -> str:
    """Plan view with the FRONT at the bottom of the picture."""
    scale = 2.0  # px per mm
    pad = 40
    lean_l, lean_r = res.lean("left", res.height), res.lean("right", res.height)
    lean_f, lean_b = res.lean("front", res.height), res.lean("back", res.height)
    gx0, gx1 = -lean_l, res.outer_width + lean_r
    gy0, gy1 = -lean_f, res.outer_depth + lean_b
    W = (gx1 - gx0) * scale + 2 * pad
    H = (gy1 - gy0) * scale + 2 * pad + 30

    def X(x: float) -> float:
        return pad + (x - gx0) * scale

    def Y(y: float) -> float:
        return pad + (gy1 - y) * scale

    def rect(x0, y0, x1, y1, **attrs) -> str:
        a = " ".join(f'{k.replace("_", "-")}="{v}"' for k, v in attrs.items())
        return (f'<rect x="{X(x0):.1f}" y="{Y(y1):.1f}" width="{(x1 - x0) * scale:.1f}" '
                f'height="{(y1 - y0) * scale:.1f}" {a}/>')

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W:.0f}" height="{H:.0f}" '
           f'viewBox="0 0 {W:.0f} {H:.0f}" font-family="Arial, sans-serif">',
           f'<rect width="100%" height="100%" fill="#ffffff"/>']
    # Top outline (dashed) if the walls lean, then the floor outline.
    if any(v > 0.01 for v in (lean_l, lean_r, lean_f, lean_b)):
        out.append(rect(gx0, gy0, gx1, gy1, fill="none", stroke="#999", stroke_dasharray="4 3"))
    out.append(rect(0, 0, res.outer_width, res.outer_depth, fill="#e8e4dc", stroke="#333", stroke_width=1.5))
    p = res.perimeter
    out.append(rect(p, p, p + res.interior_width, p + res.interior_depth, fill="#d6d1c6", stroke="none"))

    # Section regions.
    for i, s in enumerate(sections):
        r = s.region
        x0 = max(-lean_l, r.x0 + p) if not math.isinf(r.x0) else gx0
        x1 = min(gx1, r.x1 + p) if not math.isinf(r.x1) else gx1
        y0 = max(-lean_f, r.y0 + p) if not math.isinf(r.y0) else gy0
        y1 = min(gy1, r.y1 + p) if not math.isinf(r.y1) else gy1
        col = SECTION_COLOURS[i % len(SECTION_COLOURS)]
        out.append(rect(x0, y0, x1, y1, fill=col, fill_opacity="0.10", stroke=col, stroke_width=2))
        out.append(f'<text x="{X(x0) + 14:.1f}" y="{Y(y1) + 28:.1f}" font-size="16" font-weight="bold" '
                   f'fill="{col}" stroke="#ffffff" stroke-width="3" paint-order="stroke">'
                   f'{escape(s.name.split("-of-")[0])}</text>')

    # Compartments.
    for c in res.compartments:
        out.append(rect(c.x0 + p, c.y0 + p, c.x1 + p, c.y1 + p, fill="#ffffff", stroke="#555", stroke_width=0.8))
        cx, cy = X(p + (c.x0 + c.x1) / 2), Y(p + (c.y0 + c.y1) / 2)
        out.append(f'<text x="{cx:.1f}" y="{cy - 3:.1f}" font-size="12" text-anchor="middle" '
                   f'fill="#222">{escape(c.label)}</text>')
        out.append(f'<text x="{cx:.1f}" y="{cy + 12:.1f}" font-size="10" text-anchor="middle" '
                   f'fill="#555">{c.width:.1f} × {c.depth:.1f}</text>')

    title = f"{res.spec.label}  ·  outside {res.outer_width:.1f} × {res.outer_depth:.1f} mm at floor  ·  FRONT ↓"
    out.append(f'<text x="{pad}" y="{H - 12:.0f}" font-size="13" fill="#222">{escape(title)}</text>')
    out.append("</svg>")
    return "\n".join(out)
