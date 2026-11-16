"""Resolve a design into exact millimetre geometry and check the wall network.

Coordinate conventions (used everywhere in the generator):
  * Millimetres. X = width (left to right), Y = depth (front to back), Z = up.
  * "Front" is the side nearest the person when the drawer is open.
  * Global origin: front-left corner of the organizer's outside, at the floor.
  * Compartment positions use INTERIOR coordinates: origin at the inside
    front-left corner of the perimeter wall, measured at floor level.
  * Compartment sizes are CLEAR inside sizes (the usable space).

Wall rules:
  * Two compartments facing each other exactly one divider thickness apart
    share one divider wall (never two walls).
  * A compartment touching the inside of the perimeter uses the perimeter wall.
  * Otherwise there must be a usable open gap (min_open_gap_mm) so no
    unusable slivers are created. Unused floor stays as floor (no holes).

Two layout input styles resolve to the same compartment rectangles:
  * "compartments": explicit rectangles (what a visual editor will save).
  * "rows" / "columns": nested splits, convenient for hand-written designs.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .errors import Problems
from .spec import Spec
from .units import to_mm

TOL = 0.02  # mm: positions closer than this are treated as equal


@dataclass
class Compartment:
    id: str
    label: str
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def depth(self) -> float:
        return self.y1 - self.y0

    @property
    def centre(self) -> tuple[float, float]:
        return (self.x0 + self.x1) / 2, (self.y0 + self.y1) / 2

    def as_dict(self) -> dict:
        return {"id": self.id, "label": self.label, "x": round(self.x0, 3), "y": round(self.y0, 3),
                "width": round(self.width, 3), "depth": round(self.depth, 3)}


@dataclass
class Resolved:
    spec: Spec
    outer_width: float        # outside size at the floor
    outer_depth: float
    height: float
    outer_radius: float
    perimeter: float
    divider: float
    floor: float
    interior_width: float     # inside size at floor level
    interior_depth: float
    angles: dict[str, float]  # outward lean of each side, degrees
    compartments: list[Compartment]
    shared_walls: list[tuple[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def lean(self, side: str, z: float) -> float:
        """How far the outside wall on `side` has moved outward at height z."""
        return z * math.tan(math.radians(self.angles[side]))

    def flush(self, c: Compartment) -> dict[str, bool]:
        return {
            "left": abs(c.x0) <= TOL,
            "right": abs(c.x1 - self.interior_width) <= TOL,
            "front": abs(c.y0) <= TOL,
            "back": abs(c.y1 - self.interior_depth) <= TOL,
        }

    def by_id(self, cid: str) -> Compartment | None:
        return next((c for c in self.compartments if c.id == cid), None)


def resolve(spec: Spec) -> Resolved:
    p = Problems()
    cons = spec.construction
    outer_w = spec.drawer_width - 2 * spec.fit_clearance
    outer_d = spec.drawer_depth - 2 * spec.fit_clearance
    inner_w = outer_w - 2 * cons.perimeter_wall_mm
    inner_d = outer_d - 2 * cons.perimeter_wall_mm
    outer_r = max(spec.drawer_corner_radius - spec.fit_clearance, 0.0)

    if spec.organizer_height <= cons.floor_mm + 2:
        p.add(f"The organizer height ({spec.organizer_height:.1f} mm) is too low for a "
              f"{cons.floor_mm} mm floor.")

    comps = _read_layout(spec, inner_w, inner_d, p)
    res = Resolved(
        spec=spec, outer_width=outer_w, outer_depth=outer_d, height=spec.organizer_height,
        outer_radius=outer_r, perimeter=cons.perimeter_wall_mm, divider=cons.divider_wall_mm,
        floor=cons.floor_mm, interior_width=inner_w, interior_depth=inner_d,
        angles={s: getattr(spec.taper, s) for s in ("left", "right", "front", "back")},
        compartments=comps,
    )
    if comps:
        _check_compartments(res, p)
    if not comps and not p:
        p.add("The layout has no compartments.")
    for side, a in res.angles.items():
        if a > 15:
            res.warnings.append(f"The {side} wall leans {a:.1f}°, which is steep. Check the fit with a test print.")
    p.raise_if_any()
    return res


# --------------------------------------------------------------------------- input


def _read_layout(spec: Spec, inner_w: float, inner_d: float, p: Problems) -> list[Compartment]:
    layout = spec.layout
    styles = [k for k in ("compartments", "rows", "columns") if k in layout]
    extra = set(layout) - {"compartments", "rows", "columns"}
    if extra:
        p.add(f'Unknown setting(s) in "layout": {", ".join(sorted(extra))}.')
    if len(styles) != 1:
        p.add('"layout" must contain exactly one of "compartments", "rows" or "columns".')
        return []
    style = styles[0]
    if style == "compartments":
        comps = _read_rectangles(layout["compartments"], spec.units, p)
    else:
        comps = []
        counter = [0]
        _split(layout, 0.0, 0.0, inner_w, inner_d, spec, comps, counter, "layout", p)
    ids = [c.id for c in comps]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        p.add(f"Compartment ids must be unique; repeated: {', '.join(dupes)}.")
    return comps


def _read_rectangles(items, units: str, p: Problems) -> list[Compartment]:
    if not isinstance(items, list):
        p.add('"compartments" must be a list.')
        return []
    comps = []
    for i, item in enumerate(items, 1):
        where = f"compartment {i}"
        if not isinstance(item, dict):
            p.add(f"{where} must be a section with x, y, width and depth.")
            continue
        extra = set(item) - {"id", "label", "x", "y", "width", "depth"}
        if extra:
            p.add(f"Unknown setting(s) in {where}: {', '.join(sorted(extra))}.")
        vals = {}
        for k in ("x", "y", "width", "depth"):
            if k not in item:
                p.add(f'{where} is missing "{k}".')
                continue
            try:
                vals[k] = to_mm(item[k], units)
            except ValueError as e:
                p.add(f'{where} "{k}": {e}.')
        if len(vals) < 4:
            continue
        cid = str(item.get("id", f"C{i}"))
        comps.append(Compartment(cid, str(item.get("label", cid)), vals["x"], vals["y"],
                                 vals["x"] + vals["width"], vals["y"] + vals["depth"]))
    return comps


def _split(node: dict, x0: float, y0: float, w: float, d: float, spec: Spec,
           out: list[Compartment], counter: list[int], where: str, p: Problems) -> None:
    """Resolve a nested "rows"/"columns" node into compartments."""
    t = spec.construction.divider_wall_mm
    if "columns" in node:
        parts, along, size = node["columns"], "x", w
    elif "rows" in node:
        parts, along, size = node["rows"], "y", d
    else:
        p.add(f"{where} needs \"rows\" or \"columns\".")
        return
    if not isinstance(parts, list) or not parts:
        p.add(f"{where}: the list of parts is empty.")
        return
    fixed, weights, sizes = 0.0, 0.0, []
    for i, part in enumerate(parts, 1):
        if not isinstance(part, dict):
            p.add(f"{where} part {i} must be a section.")
            return
        extra = set(part) - {"id", "label", "size", "fill", "rows", "columns"}
        if extra:
            p.add(f"Unknown setting(s) in {where} part {i}: {', '.join(sorted(extra))}.")
        if "size" in part:
            if "fill" in part:
                p.add(f'{where} part {i}: give either "size" or "fill", not both.')
            try:
                s = to_mm(part["size"], spec.units)
            except ValueError as e:
                p.add(f'{where} part {i} "size": {e}.')
                return
            fixed += s
            sizes.append(("fixed", s))
        else:
            wgt = part.get("fill", 1)
            if isinstance(wgt, bool) or not isinstance(wgt, (int, float)) or wgt <= 0:
                p.add(f'{where} part {i}: "fill" must be a positive number (a share of the leftover space).')
                return
            weights += wgt
            sizes.append(("fill", float(wgt)))
    walls = (len(parts) - 1) * t
    leftover = size - walls - fixed
    axis_name = "width" if along == "x" else "depth"
    if weights == 0 and abs(leftover) > TOL:
        p.add(f"{where}: the sizes add up to {fixed + walls:.2f} mm including {len(parts) - 1} divider(s), "
              f"but the available {axis_name} is {size:.2f} mm ({leftover:+.2f} mm). "
              'Mark one part as "fill" to take up the difference, or correct the sizes.')
        return
    if weights > 0 and leftover <= 0:
        p.add(f"{where}: the fixed sizes ({fixed:.1f} mm) plus dividers ({walls:.1f} mm) "
              f"already use the whole {axis_name} ({size:.1f} mm), leaving nothing for the \"fill\" parts.")
        return
    pos = x0 if along == "x" else y0
    for i, (part, (kind, val)) in enumerate(zip(parts, sizes), 1):
        s = val if kind == "fixed" else leftover * val / weights
        if along == "x":
            px, py, pw, pd = pos, y0, s, d
        else:
            px, py, pw, pd = x0, pos, w, s
        if "rows" in part or "columns" in part:
            _split(part, px, py, pw, pd, spec, out, counter, f"{where} part {i}", p)
        else:
            counter[0] += 1
            cid = str(part.get("id", f"C{counter[0]}"))
            out.append(Compartment(cid, str(part.get("label", cid)), px, py, px + pw, py + pd))
        pos += s + t


# --------------------------------------------------------------------------- checks


def _check_compartments(res: Resolved, p: Problems) -> None:
    cons = res.spec.construction
    t = res.divider
    min_c, min_open = cons.min_compartment_mm, cons.min_open_gap_mm
    W, D = res.interior_width, res.interior_depth
    comps = res.compartments

    for c in comps:
        if c.width < min_c - TOL or c.depth < min_c - TOL:
            p.add(f'Compartment "{c.id}" is {c.width:.1f} × {c.depth:.1f} mm; the minimum is {min_c:.0f} mm each way.')
        if c.x0 < -TOL or c.y0 < -TOL or c.x1 > W + TOL or c.y1 > D + TOL:
            p.add(f'Compartment "{c.id}" extends outside the organizer interior '
                  f"({W:.1f} × {D:.1f} mm inside the perimeter wall).")
            continue
        # Distance to each perimeter side: touch it, or leave a usable gap.
        for side, gap in (("left", c.x0), ("right", W - c.x1), ("front", c.y0), ("back", D - c.y1)):
            if TOL < gap < t + min_open - TOL:
                p.add(f'Compartment "{c.id}" is {gap:.2f} mm from the {side} perimeter wall. '
                      f"Either touch the wall (0 mm) or leave at least {t + min_open:.1f} mm "
                      f"({t:.1f} mm divider + {min_open:.0f} mm usable space).")

    for i, a in enumerate(comps):
        for b in comps[i + 1:]:
            ox = min(a.x1, b.x1) - max(a.x0, b.x0)   # overlap along x
            oy = min(a.y1, b.y1) - max(a.y0, b.y0)   # overlap along y
            if ox > TOL and oy > TOL:
                p.add(f'Compartments "{a.id}" and "{b.id}" overlap by {ox:.1f} × {oy:.1f} mm.')
                continue
            for gap, overlap in ((-ox, oy), (-oy, ox)):
                if overlap <= TOL or gap < -TOL:
                    continue
                pair = f'"{a.id}" and "{b.id}"'
                if abs(gap - t) <= TOL:
                    res.shared_walls.append((a.id, b.id))
                elif gap < t - TOL:
                    p.add(f"Compartments {pair} are only {gap:.2f} mm apart. A shared divider needs exactly "
                          f"{t:.2f} mm between them.")
                elif gap < 2 * t + min_open - TOL:
                    p.add(f"Compartments {pair} are {gap:.2f} mm apart, which leaves an unusable sliver. "
                          f"Use exactly {t:.2f} mm (one shared divider) or at least {2 * t + min_open:.1f} mm.")
