"""3D geometry (build123d / OpenCascade).

Construction method (proven in the Stage 0 feasibility test):
  1. Outer body: a ruled loft from the floor outline to the top outline, so
     each outside wall can lean by its own angle. Bottom edge chamfered.
  2. Shell: outer body minus the interior cavity (cavity starts at floor
     height, so the floor stays solid and continuous).
  3. Dividers: a 2D wall network made from a frame of divider thickness
     around every compartment, minus all compartment spaces. Where a
     compartment touches the perimeter, its walls are extended outward so
     they always meet a leaning outside wall. The network is extruded,
     trimmed to the outer body and fused with the shell. Shared walls come
     out as one wall because neighbouring frames overlap exactly.
  4. Top edges rounded (fillet).
  5. Sections: the finished organizer intersected with each section region.

Global coordinates: origin at the outside front-left corner at the floor.
"""

from __future__ import annotations

import math

from build123d import (
    Axis,
    Box,
    Part,
    Plane,
    Pos,
    Rectangle,
    RectangleRounded,
    chamfer,
    extrude,
    fillet,
    loft,
)

from .layout import Resolved
from .seams import Region

FAR = 2000.0  # stands in for "infinitely far" when cutting sections


def _outline(x0: float, y0: float, x1: float, y1: float, r: float, z: float):
    w, d = x1 - x0, y1 - y0
    shape = RectangleRounded(w, d, r) if r > 0.05 else Rectangle(w, d)
    return Plane.XY.offset(z) * Pos((x0 + x1) / 2, (y0 + y1) / 2) * shape


def _box_outline(res: Resolved, inset: float, z: float, radius: float):
    """Outline of the outside (inset=0) or inside (inset=perimeter) at height z."""
    return _outline(
        inset - res.lean("left", z),
        inset - res.lean("front", z),
        res.outer_width - inset + res.lean("right", z),
        res.outer_depth - inset + res.lean("back", z),
        radius,
        z,
    )


def build_outer(res: Resolved) -> Part:
    outer = loft([_box_outline(res, 0, 0, res.outer_radius),
                  _box_outline(res, 0, res.height, res.outer_radius)], ruled=True)
    c = res.spec.construction.bottom_chamfer_mm
    if c > 0:
        outer = chamfer(outer.edges().group_by(Axis.Z)[0], c)
    return outer


def build_organizer(res: Resolved) -> tuple[Part, list[str]]:
    warnings: list[str] = []
    outer = build_outer(res)

    inner_r = res.outer_radius - res.perimeter
    inner_r = inner_r if inner_r > 0.3 else 0.0
    z_top = res.height + 1.0
    cavity = loft([_box_outline(res, res.perimeter, res.floor, inner_r),
                   _box_outline(res, res.perimeter, z_top, inner_r)], ruled=True)
    body = outer - cavity

    walls = _divider_network(res)
    if walls is not None:
        dividers = extrude(walls, res.height) & outer
        body = body + dividers

    r = res.spec.construction.top_edge_radius_mm
    if r > 0:
        top_edges = body.edges().group_by(Axis.Z)[-1]
        try:
            rounded = fillet(top_edges, r)
            if rounded.is_valid:
                body = rounded
            else:
                warnings.append("The top edges could not be rounded cleanly, so they were left square.")
        except Exception:  # OpenCascade reports fillet failures as generic errors
            warnings.append("The top edges could not be rounded, so they were left square.")

    if isinstance(body, Part) is False:
        body = Part(body.wrapped)
    return body, warnings


def _divider_network(res: Resolved):
    """2D sketch of every divider wall (global coordinates), or None."""
    t = res.divider
    max_lean = max(res.lean(s, res.height + 1) for s in ("left", "right", "front", "back"))
    reach = res.perimeter + max_lean + 5.0  # far enough to meet any leaning outside wall
    ox = oy = res.perimeter                 # interior origin in global coordinates
    frames = spaces = None
    for c in res.compartments:
        f = res.flush(c)
        fx0 = c.x0 - (reach if f["left"] else t)
        fx1 = c.x1 + (reach if f["right"] else t)
        fy0 = c.y0 - (reach if f["front"] else t)
        fy1 = c.y1 + (reach if f["back"] else t)
        frame = Pos(ox + (fx0 + fx1) / 2, oy + (fy0 + fy1) / 2) * Rectangle(fx1 - fx0, fy1 - fy0)
        sx0 = c.x0 - (reach if f["left"] else 0)
        sx1 = c.x1 + (reach if f["right"] else 0)
        sy0 = c.y0 - (reach if f["front"] else 0)
        sy1 = c.y1 + (reach if f["back"] else 0)
        space = Pos(ox + (sx0 + sx1) / 2, oy + (sy0 + sy1) / 2) * Rectangle(sx1 - sx0, sy1 - sy0)
        frames = frame if frames is None else frames + frame
        spaces = space if spaces is None else spaces + space
    if frames is None:
        return None
    walls = frames - spaces
    if not walls.faces() or walls.area < 1e-6:
        return None
    return walls


def region_solid(res: Resolved, region: Region) -> Part:
    """A tall box covering one section's region (global coordinates)."""
    def g(v: float, offset: float) -> float:
        if math.isinf(v):
            return math.copysign(FAR, v)
        return v + offset

    x0, x1 = g(region.x0, res.perimeter), g(region.x1, res.perimeter)
    y0, y1 = g(region.y0, res.perimeter), g(region.y1, res.perimeter)
    h = res.height + 10
    return Pos((x0 + x1) / 2, (y0 + y1) / 2, res.height / 2) * Box(x1 - x0, y1 - y0, h)


def cut_section(body: Part, res: Resolved, region: Region) -> Part:
    piece = body & region_solid(res, region)
    if not isinstance(piece, Part):
        piece = Part(piece.wrapped)
    return piece
